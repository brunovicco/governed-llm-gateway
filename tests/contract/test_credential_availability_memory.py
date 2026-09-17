"""Process-local reference conformance, not serving or distributed-store proof."""

import asyncio
import traceback
from collections.abc import AsyncGenerator, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from typing import cast
from uuid import UUID

import pytest
from governed_llm_gateway_core.adapters import credential_availability_memory as memory
from governed_llm_gateway_core.adapters.credential_availability_memory import (
    InMemoryCredentialAvailabilityReader,
    InMemoryCredentialAvailabilityState,
    InMemoryCredentialAvailabilityWorker,
    InMemoryCredentialGenerationPublisher,
)
from governed_llm_gateway_core.application.credential_availability import (
    CredentialAvailabilityError,
    CredentialAvailabilityErrorCode,
    CredentialAvailabilityPort,
    CredentialAvailabilityReadPort,
    CredentialGenerationPublisher,
)
from governed_llm_gateway_core.domain.credential_availability import (
    CredentialAdmission,
    CredentialAvailabilityState,
    CredentialBindingRejection,
    CredentialCompletionReceipt,
    CredentialContractError,
    CredentialGeneration,
    CredentialGenerationPublication,
    CredentialRejectionEvidence,
)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Backend:
    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or Clock()
        self.state = InMemoryCredentialAvailabilityState(
            validation_lease_seconds=10.0, clock=self.clock
        )
        self.first: CredentialAvailabilityPort = InMemoryCredentialAvailabilityWorker(self.state)
        self.second: CredentialAvailabilityPort = InMemoryCredentialAvailabilityWorker(self.state)
        self.reader: CredentialAvailabilityReadPort = InMemoryCredentialAvailabilityReader(
            self.state
        )
        self.publisher: CredentialGenerationPublisher = InMemoryCredentialGenerationPublisher(
            self.state
        )


def _generation(
    *,
    epoch: int = 1,
    material: str = "material-a",
    binding: str = "binding-a",
    version: str = "version-a",
) -> CredentialGeneration:
    return CredentialGeneration(
        binding_id=binding,
        epoch=epoch,
        material_id=material,
        secret_version_id=version,
        runtime_digest="sha256:" + "a" * 64,
        auth_scope_digest="sha256:" + "b" * 64,
    )


def _rejection(generation: CredentialGeneration) -> CredentialBindingRejection:
    return CredentialBindingRejection(
        generation,
        CredentialRejectionEvidence.AUTHENTICATION_BOUNDARY_REJECTED,
        "reviewed-synthetic-classifier",
    )


def _replace_metadata[T](value: T, **changes: object) -> T:
    """Exercise dynamic fixture dimensions at the runtime-validation boundary."""
    apply_changes = cast(Callable[..., T], replace)
    return apply_changes(value, **changes)


async def _publish(
    backend: Backend, generation: CredentialGeneration, previous: CredentialGeneration | None = None
) -> None:
    assert await backend.publisher.publish(CredentialGenerationPublication(generation, previous))


async def _validate(
    backend: Backend, generation: CredentialGeneration
) -> tuple[CredentialAdmission, CredentialCompletionReceipt]:
    owner = await backend.first.admit(generation, attempt_id="validation-attempt")
    assert owner is not None and owner.is_validation
    receipt = await backend.first.complete_validation(owner)
    assert receipt is not None
    return owner, receipt


def test_unknown_state_denies_and_actual_capabilities_are_separate() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        snapshot = await backend.reader.snapshot(generation.binding_id)
        assert snapshot.state is CredentialAvailabilityState.UNKNOWN
        assert not snapshot.is_candidate_eligible(generation)
        assert await backend.first.admit(generation, attempt_id="attempt") is None
        assert not hasattr(backend.reader, "admit")
        assert not hasattr(backend.first, "publish")
        assert not hasattr(backend.publisher, "admit")
        assert (
            await backend.first.complete_validation(CredentialAdmission(generation, "attempt"))
            is None
        )
        with pytest.raises(CredentialAvailabilityError) as error:
            await backend.first.record_rejection(_rejection(generation))
        assert error.value.code is CredentialAvailabilityErrorCode.INVALID_STATE
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.UNKNOWN

    asyncio.run(scenario())


def test_concurrent_claims_have_one_owner_and_reads_never_claim_or_renew() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        for _ in range(3):
            assert (await backend.reader.snapshot(generation.binding_id)).is_candidate_eligible(
                generation
            )
        results = await asyncio.gather(
            *(
                worker.admit(generation, attempt_id=f"attempt-{index}")
                for index, worker in enumerate([backend.first, backend.second] * 16)
            )
        )
        admitted = [item for item in results if item is not None]
        assert len(admitted) == 1
        owner = admitted[0]
        assert owner.validation_timeout_seconds == 10.0
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.VALIDATING
        backend.clock.now += 2.0
        recheck = await backend.second.admit(generation, attempt_id=owner.attempt_id)
        assert recheck is not None
        assert recheck.validation_fence == owner.validation_fence
        assert recheck.validation_timeout_seconds == 8.0
        assert await backend.first.is_admitted(owner)
        assert await backend.second.is_admitted(recheck)
        assert await backend.second.admit(generation, attempt_id="another") is None
        backend.clock.now += 8.0
        assert not await backend.first.is_admitted(owner)
        assert not await backend.second.is_admitted(recheck)

    asyncio.run(scenario())


def test_shared_state_serializes_threads_with_independent_event_loops() -> None:
    backend = Backend()
    generation = _generation()
    asyncio.run(_publish(backend, generation))
    barrier = Barrier(16)

    def claim(index: int) -> CredentialAdmission | None:
        barrier.wait(timeout=10)
        return asyncio.run(backend.first.admit(generation, attempt_id=f"thread-{index}"))

    with ThreadPoolExecutor(max_workers=16) as pool:
        admitted = [item for item in pool.map(claim, range(16)) if item is not None]
    assert len(admitted) == 1
    assert asyncio.run(backend.second.is_admitted(admitted[0]))


def test_expiry_at_exact_boundary_fences_old_owner_even_with_reused_attempt_id() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="same-attempt")
        assert owner is not None
        backend.clock.now = 109.999
        assert await backend.first.is_admitted(owner)
        assert await backend.second.admit(generation, attempt_id="other") is None
        backend.clock.now = 110.0
        for _ in range(3):
            assert (
                await backend.reader.snapshot(generation.binding_id)
            ).state is CredentialAvailabilityState.PENDING_VALIDATION
        assert not await backend.first.is_admitted(owner)
        replacement = await backend.second.admit(generation, attempt_id="same-attempt")
        assert replacement is not None
        assert replacement.validation_fence != owner.validation_fence
        await backend.first.release(owner)
        assert await backend.first.complete_validation(owner) is None
        assert await backend.second.is_admitted(replacement)
        assert await backend.first.admit(generation, attempt_id="other") is None
        assert await backend.second.complete_validation(replacement) is not None

    asyncio.run(scenario())


def test_completion_is_idempotent_and_receipt_outlives_only_its_own_retired_lease() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner, receipt = await _validate(backend, generation)
        assert receipt.matches_admission(owner)
        assert not await backend.second.is_admitted(owner)
        backend.clock.now += 1000.0
        assert await backend.second.is_completion_current(receipt)
        assert await backend.second.complete_validation(owner) == receipt
        await backend.first.release(owner)
        assert await backend.second.is_completion_current(receipt)
        for forged in (
            replace(receipt, completion_fence="fabricated-fence"),
            replace(receipt, validation_fence="fabricated-owner"),
            replace(receipt, attempt_id="other-attempt"),
            replace(receipt, generation=replace(generation, epoch=2)),
        ):
            assert not await backend.second.is_completion_current(forged)
        rotated = _generation(epoch=2, material="material-b")
        await _publish(backend, rotated, generation)
        assert not await backend.second.is_completion_current(receipt)
        assert await backend.second.complete_validation(owner) is None

    asyncio.run(scenario())


def test_available_attempts_are_concurrent_but_cannot_promote_or_undo_quarantine() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner, receipt = await _validate(backend, generation)
        admissions = await asyncio.gather(
            *(
                backend.second.admit(generation, attempt_id=f"ordinary-{index}")
                for index in range(16)
            )
        )
        assert all(item is not None and not item.is_validation for item in admissions)
        for item in admissions:
            assert item is not None
            await backend.first.release(item)
            assert await backend.first.is_admitted(item)
            assert await backend.first.complete_validation(item) is None
        await backend.second.record_rejection(_rejection(generation))
        await backend.second.record_rejection(_rejection(generation))
        assert not await backend.first.is_completion_current(receipt)
        assert await backend.first.complete_validation(owner) is None
        for item in admissions:
            assert item is not None
            assert not await backend.first.is_admitted(item)
            assert await backend.first.complete_validation(item) is None
        assert await backend.first.admit(generation, attempt_id="new") is None
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.QUARANTINED

    asyncio.run(scenario())


def test_finally_release_on_task_cancellation_is_neutral_and_fenced() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        ready = asyncio.Event()
        never = asyncio.Event()
        captured: list[CredentialAdmission] = []

        async def caller() -> None:
            owner = await backend.first.admit(generation, attempt_id="cancelled")
            assert owner is not None
            captured.append(owner)
            try:
                ready.set()
                await never.wait()
            finally:
                await backend.first.release(owner)

        task = asyncio.create_task(caller())
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.PENDING_VALIDATION
        replacement = await backend.second.admit(generation, attempt_id="replacement")
        assert replacement is not None
        await backend.first.release(captured[0])
        assert await backend.first.complete_validation(captured[0]) is None
        assert await backend.second.is_admitted(replacement)

    asyncio.run(scenario())


def test_local_exception_finally_release_does_not_prove_provider_recovery() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="failed-locally")
        assert owner is not None
        with pytest.raises(RuntimeError, match="local failure"):
            try:
                raise RuntimeError("local failure")
            finally:
                await backend.first.release(owner)
        assert not await backend.second.is_admitted(owner)
        assert await backend.second.complete_validation(owner) is None
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.PENDING_VALIDATION
        replacement = await backend.second.admit(generation, attempt_id="replacement")
        assert replacement is not None
        await backend.first.release(owner)
        assert await backend.second.is_admitted(replacement)

    asyncio.run(scenario())


@pytest.mark.parametrize("target_state", ["pending", "validating", "available"])
def test_late_rejection_blocks_same_material_reactivated_under_a_new_epoch(
    target_state: str,
) -> None:
    async def scenario() -> None:
        backend = Backend()
        previous = _generation()
        await _publish(backend, previous)
        await _validate(backend, previous)
        current = _generation(epoch=2, version="new-version-alias")
        await _publish(backend, current, previous)
        owner = None
        if target_state != "pending":
            owner = await backend.second.admit(current, attempt_id="new-validation")
            assert owner is not None
            if target_state == "available":
                assert await backend.second.complete_validation(owner) is not None
        await backend.first.record_rejection(_rejection(previous))
        assert (
            await backend.reader.snapshot(current.binding_id)
        ).state is CredentialAvailabilityState.QUARANTINED
        assert await backend.second.admit(current, attempt_id="retry") is None
        if owner is not None:
            assert not await backend.second.is_admitted(owner)
            await backend.second.release(owner)
            assert await backend.second.complete_validation(owner) is None
        assert await backend.publisher.publish(CredentialGenerationPublication(current, previous))
        assert (
            await backend.reader.snapshot(current.binding_id)
        ).state is CredentialAvailabilityState.QUARANTINED

    asyncio.run(scenario())


def test_retired_material_rejection_spares_distinct_material_and_survives_rollback() -> None:
    async def scenario() -> None:
        backend = Backend()
        previous = _generation()
        await _publish(backend, previous)
        old_owner = await backend.first.admit(previous, attempt_id="old-owner")
        assert old_owner is not None
        current = _generation(epoch=2, material="material-b")
        await _publish(backend, current, previous)
        _, receipt = await _validate(backend, current)
        await backend.first.record_rejection(_rejection(previous))
        assert await backend.second.is_completion_current(receipt)
        await backend.first.release(old_owner)
        assert await backend.first.complete_validation(old_owner) is None
        rolled_back = _generation(epoch=3, version="old-material-new-alias")
        await _publish(backend, rolled_back, current)
        assert (
            await backend.reader.snapshot(rolled_back.binding_id)
        ).state is CredentialAvailabilityState.QUARANTINED
        assert await backend.second.admit(rolled_back, attempt_id="rollback") is None
        rebuilt_worker = InMemoryCredentialAvailabilityWorker(backend.state)
        rebuilt_publisher = InMemoryCredentialGenerationPublisher(backend.state)
        relabeled = replace(rolled_back, epoch=4, runtime_digest="sha256:" + "c" * 64)
        assert await rebuilt_publisher.publish(
            CredentialGenerationPublication(relabeled, rolled_back)
        )
        assert await rebuilt_worker.admit(relabeled, attempt_id="reconstructed-worker") is None
        assert (
            await Backend().reader.snapshot(previous.binding_id)
        ).state is CredentialAvailabilityState.UNKNOWN

    asyncio.run(scenario())


def test_equal_material_labels_in_different_bindings_are_not_global_quarantine() -> None:
    async def scenario() -> None:
        backend = Backend()
        first = _generation()
        second = _generation(binding="binding-b")
        for generation in (first, second):
            await _publish(backend, generation)
            await _validate(backend, generation)
        await backend.first.record_rejection(_rejection(first))
        assert (
            await backend.reader.snapshot(first.binding_id)
        ).state is CredentialAvailabilityState.QUARANTINED
        admission = await backend.second.admit(second, attempt_id="independent")
        assert admission is not None and not admission.is_validation
        assert await backend.second.is_admitted(admission)

    asyncio.run(scenario())


def test_cas_has_one_winner_and_duplicate_intent_does_not_reset_validation() -> None:
    async def scenario() -> None:
        backend = Backend()
        previous = _generation()
        await _publish(backend, previous)
        candidates = [_generation(epoch=2, material=f"material-{index}") for index in range(16)]
        results = await asyncio.gather(
            *(
                backend.publisher.publish(CredentialGenerationPublication(item, previous))
                for item in candidates
            )
        )
        assert results.count(True) == 1
        current = candidates[results.index(True)]
        assert not await backend.publisher.publish(CredentialGenerationPublication(current))
        mismatched = replace(previous, runtime_digest="sha256:" + "c" * 64)
        assert not await backend.publisher.publish(
            CredentialGenerationPublication(current, mismatched)
        )
        owner = await backend.first.admit(current, attempt_id="owner")
        assert owner is not None
        backend.clock.now += 3.0
        await _publish(backend, current, previous)
        recheck = await backend.second.admit(current, attempt_id="owner")
        assert recheck is not None and recheck.validation_timeout_seconds == 7.0
        assert recheck.validation_fence == owner.validation_fence
        assert await backend.second.admit(previous, attempt_id="stale") is None
        assert (
            await backend.second.admit(
                replace(current, runtime_digest="sha256:" + "d" * 64), attempt_id="mismatched"
            )
            is None
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("epoch", [2**53 - 1, 2**53 + 1, 2**63 - 2])
def test_publication_preserves_exact_integer_epochs_above_float_precision(epoch: int) -> None:
    async def scenario() -> None:
        backend = Backend()
        previous = _generation(epoch=epoch)
        current = _generation(epoch=epoch + 1, material="material-b")
        await _publish(backend, previous)
        await _publish(backend, current, previous)
        snapshot = await backend.reader.snapshot(current.binding_id)
        assert snapshot.generation == current
        assert snapshot.generation.epoch == epoch + 1
        assert await backend.second.admit(previous, attempt_id="old") is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field", ["epoch", "material_id", "secret_version_id", "runtime_digest", "auth_scope_digest"]
)
def test_rejection_without_published_exact_generation_is_not_trusted(field: str) -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        _, receipt = await _validate(backend, generation)
        changes = {
            "epoch": 2,
            "material_id": "other-material",
            "secret_version_id": "other-version",
            "runtime_digest": "sha256:" + "c" * 64,
            "auth_scope_digest": "sha256:" + "d" * 64,
        }
        forged = _replace_metadata(generation, **{field: changes[field]})
        with pytest.raises(CredentialAvailabilityError) as error:
            await backend.first.record_rejection(_rejection(forged))
        assert error.value.code is CredentialAvailabilityErrorCode.INVALID_STATE
        assert await backend.second.is_completion_current(receipt)

    asyncio.run(scenario())


@pytest.mark.parametrize("value", [True, None, "100", -1.0, float("nan"), float("inf"), 10**400])
@pytest.mark.parametrize("operation", ["snapshot", "admit", "is_admitted", "complete_validation"])
def test_invalid_clock_fails_closed_without_raw_details(value: object, operation: str) -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="owner")
        assert owner is not None
        backend.clock.now = cast(float, value)
        with pytest.raises(CredentialAvailabilityError) as error:
            if operation == "snapshot":
                await backend.reader.snapshot(generation.binding_id)
            elif operation == "admit":
                await backend.first.admit(generation, attempt_id="owner")
            elif operation == "is_admitted":
                await backend.first.is_admitted(owner)
            else:
                await backend.first.complete_validation(owner)
        assert error.value.code is CredentialAvailabilityErrorCode.INVALID_STATE
        assert str(error.value) == "credential availability control failed"
        backend.clock.now = 101.0
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.VALIDATING
        assert await backend.first.is_admitted(owner)

    asyncio.run(scenario())


def test_backward_clock_cannot_revive_expired_ownership() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="owner")
        assert owner is not None
        backend.clock.now = 110.0
        assert not await backend.first.is_admitted(owner)
        backend.clock.now = 109.0
        with pytest.raises(CredentialAvailabilityError):
            await backend.first.complete_validation(owner)
        backend.clock.now = 110.0
        assert await backend.first.complete_validation(owner) is None
        replacement = await backend.second.admit(generation, attempt_id="owner")
        assert replacement is not None and replacement.validation_fence != owner.validation_fence

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "value", [True, False, None, "10", 0, -1, float("nan"), float("inf"), 10**400]
)
def test_invalid_configured_lease_is_rejected(value: object) -> None:
    with pytest.raises(CredentialContractError):
        InMemoryCredentialAvailabilityState(validation_lease_seconds=cast(float, value))


@pytest.mark.parametrize(("now", "lease"), [(1e308, 1e308), (1e20, 1.0)])
def test_unrepresentable_deadline_does_not_claim_owner(now: float, lease: float) -> None:
    async def scenario() -> None:
        clock = Clock()
        clock.now = now
        state = InMemoryCredentialAvailabilityState(validation_lease_seconds=lease, clock=clock)
        worker = InMemoryCredentialAvailabilityWorker(state)
        publisher = InMemoryCredentialGenerationPublisher(state)
        generation = _generation()
        assert await publisher.publish(CredentialGenerationPublication(generation))
        with pytest.raises(CredentialAvailabilityError):
            await worker.admit(generation, attempt_id="owner")
        assert (
            await worker.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.PENDING_VALIDATION

    asyncio.run(scenario())


@pytest.mark.parametrize("corruption", ["missing", "wrong-type"])
@pytest.mark.parametrize(
    "operation", ["snapshot", "admit", "release", "complete_validation", "publish"]
)
def test_lost_or_corrupt_known_state_is_never_reset(corruption: str, operation: str) -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="owner")
        assert owner is not None
        records = cast(dict[str, object], backend.state._records)
        if corruption == "missing":
            del records[generation.binding_id]
        else:
            records[generation.binding_id] = "private-corrupt-record"
        with pytest.raises(CredentialAvailabilityError) as error:
            if operation == "snapshot":
                await backend.reader.snapshot(generation.binding_id)
            elif operation == "admit":
                await backend.first.admit(generation, attempt_id="other")
            elif operation == "release":
                await backend.first.release(owner)
            elif operation == "complete_validation":
                await backend.first.complete_validation(owner)
            else:
                await backend.publisher.publish(CredentialGenerationPublication(generation))
        assert error.value.code is CredentialAvailabilityErrorCode.INVALID_STATE
        assert "private-corrupt-record" not in str(error.value)

    asyncio.run(scenario())


def test_clock_exception_is_sanitized_but_rejection_and_cleanup_do_not_need_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_clock() -> float:
        raise RuntimeError("private-clock-error-must-not-leak")

    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="owner")
        assert owner is not None
        monkeypatch.setattr(backend.state, "_clock", fail_clock)
        with pytest.raises(CredentialAvailabilityError) as error:
            await backend.first.complete_validation(owner)
        assert error.value.code is CredentialAvailabilityErrorCode.UNAVAILABLE
        assert error.value.__cause__ is None and error.value.__suppress_context__
        assert "private-clock-error-must-not-leak" not in "".join(
            traceback.format_exception(error.value)
        )
        await backend.first.record_rejection(_rejection(generation))
        await backend.first.release(owner)
        monkeypatch.setattr(backend.state, "_clock", backend.clock)
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.QUARANTINED

    asyncio.run(scenario())


def test_fence_failure_does_not_publish_available_or_echo_raw_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_fence() -> UUID:
        raise RuntimeError("private-fence-error-must-not-leak")

    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="owner")
        assert owner is not None
        monkeypatch.setattr(memory, "uuid4", fail_fence)
        with pytest.raises(CredentialAvailabilityError) as error:
            await backend.first.complete_validation(owner)
        assert error.value.code is CredentialAvailabilityErrorCode.UNAVAILABLE
        assert "private-fence-error-must-not-leak" not in "".join(
            traceback.format_exception(error.value)
        )
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.VALIDATING
        await backend.first.release(owner)
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.PENDING_VALIDATION

    asyncio.run(scenario())


def test_default_repr_and_operations_emit_no_internal_metadata(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation(
            binding="private-binding-marker",
            material="private-material-marker",
            version="private-version-marker",
        )
        await _publish(backend, generation)
        _, receipt = await _validate(backend, generation)
        await backend.first.record_rejection(_rejection(generation))
        rendered = repr((backend.state, backend.first, backend.reader, backend.publisher, receipt))
        assert all(
            marker not in rendered
            for marker in (
                generation.binding_id,
                generation.material_id,
                generation.secret_version_id,
                receipt.completion_fence,
            )
        )

    asyncio.run(scenario())
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert not caplog.records


def test_closing_caller_generator_releases_without_recovery() -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)

        async def caller() -> AsyncGenerator[None]:
            owner = await backend.first.admit(generation, attempt_id="closing-caller")
            assert owner is not None
            try:
                yield None
            finally:
                await backend.first.release(owner)

        iterator = caller()
        await anext(iterator)
        await iterator.aclose()
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.PENDING_VALIDATION
        assert await backend.second.admit(generation, attempt_id="replacement") is not None

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["collision", "wrong-type", "exception"])
def test_fence_fault_before_admission_leaves_pending_state(
    fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed = UUID("00000000-0000-4000-8000-000000000001")

    def fail() -> UUID:
        raise RuntimeError("private-id-source-failure")

    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        monkeypatch.setattr(memory, "uuid4", lambda: fixed)
        first = await backend.first.admit(generation, attempt_id="first")
        assert first is not None
        await backend.first.release(first)
        if fault == "wrong-type":
            monkeypatch.setattr(memory, "uuid4", lambda: "private-invalid-id")
        elif fault == "exception":
            monkeypatch.setattr(memory, "uuid4", fail)
        with pytest.raises(CredentialAvailabilityError) as error:
            await backend.second.admit(generation, attempt_id="replacement")
        expected = (
            CredentialAvailabilityErrorCode.UNAVAILABLE
            if fault == "exception"
            else CredentialAvailabilityErrorCode.INVALID_STATE
        )
        assert error.value.code is expected
        assert "private-" not in "".join(traceback.format_exception(error.value))
        assert (
            await backend.reader.snapshot(generation.binding_id)
        ).state is CredentialAvailabilityState.PENDING_VALIDATION
        assert await backend.first.complete_validation(first) is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "corruption",
    [
        "unknown-state",
        "wrong-binding",
        "missing-publication",
        "missing-owner",
        "wrong-owner",
        "invalid-deadline",
        "missing-history",
        "missing-receipt",
        "wrong-receipt",
        "unissued-receipt",
        "missing-tombstone",
    ],
)
def test_inconsistent_private_records_fail_closed(corruption: str) -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="owner")
        assert owner is not None
        if corruption in {"missing-receipt", "wrong-receipt", "unissued-receipt"}:
            assert await backend.first.complete_validation(owner) is not None
        if corruption == "missing-tombstone":
            await backend.first.record_rejection(_rejection(generation))
            backend.state._rejected.clear()
        record = backend.state._records[generation.binding_id]
        if corruption == "unknown-state":
            changed = _replace_metadata(record, state=CredentialAvailabilityState.UNKNOWN)
        elif corruption == "wrong-binding":
            changed = replace(record, generation=replace(generation, binding_id="other-binding"))
        elif corruption == "missing-publication":
            changed = _replace_metadata(record, publication=None)
        elif corruption == "missing-owner":
            changed = replace(record, owner=None)
        elif corruption == "wrong-owner":
            assert record.owner is not None
            changed = replace(
                record,
                owner=replace(record.owner, admission=CredentialAdmission(generation, "ordinary")),
            )
        elif corruption == "invalid-deadline":
            assert record.owner is not None
            changed = replace(record, owner=replace(record.owner, expires_at=float("nan")))
        elif corruption == "missing-history":
            backend.state._published.clear()
            changed = record
        elif corruption == "missing-receipt":
            changed = replace(record, receipt=None)
        elif corruption == "wrong-receipt":
            assert record.receipt is not None
            changed = replace(
                record, receipt=replace(record.receipt, generation=replace(generation, epoch=2))
            )
        elif corruption == "unissued-receipt":
            assert record.receipt is not None
            changed = replace(
                record, receipt=replace(record.receipt, completion_fence="unissued-fence")
            )
        else:
            changed = record
        backend.state._records[generation.binding_id] = changed
        with pytest.raises(CredentialAvailabilityError) as error:
            await backend.first.snapshot(generation.binding_id)
        assert error.value.code is CredentialAvailabilityErrorCode.INVALID_STATE

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "adapter",
    [
        InMemoryCredentialAvailabilityReader,
        InMemoryCredentialAvailabilityWorker,
        InMemoryCredentialGenerationPublisher,
    ],
)
def test_adapters_require_explicit_state(
    adapter: type[InMemoryCredentialAvailabilityReader]
    | type[InMemoryCredentialGenerationPublisher],
) -> None:
    with pytest.raises(CredentialContractError):
        adapter(cast(InMemoryCredentialAvailabilityState, None))


def test_state_rejects_non_callable_clock() -> None:
    with pytest.raises(CredentialContractError):
        InMemoryCredentialAvailabilityState(
            validation_lease_seconds=10.0, clock=cast(Callable[[], float], None)
        )


def test_concurrent_rejection_always_dominates_success() -> None:
    backend = Backend()
    generation = _generation()
    asyncio.run(_publish(backend, generation))
    owner = asyncio.run(backend.first.admit(generation, attempt_id="owner"))
    assert owner is not None
    barrier = Barrier(2)

    def complete() -> CredentialCompletionReceipt | None:
        barrier.wait(timeout=10)
        return asyncio.run(backend.first.complete_validation(owner))

    def reject() -> None:
        barrier.wait(timeout=10)
        asyncio.run(backend.second.record_rejection(_rejection(generation)))

    with ThreadPoolExecutor(max_workers=2) as pool:
        completion = pool.submit(complete)
        rejection = pool.submit(reject)
        receipt = completion.result(timeout=10)
        rejection.result(timeout=10)
    if receipt is not None:
        assert not asyncio.run(backend.first.is_completion_current(receipt))
    assert asyncio.run(backend.first.complete_validation(owner)) is None
    assert (
        asyncio.run(backend.reader.snapshot(generation.binding_id)).state
        is CredentialAvailabilityState.QUARANTINED
    )


@pytest.mark.parametrize("change", ["attempt", "fence", "generation", "ordinary"])
def test_fabricated_handle_cannot_complete_or_release_current_owner(change: str) -> None:
    async def scenario() -> None:
        backend = Backend()
        generation = _generation()
        await _publish(backend, generation)
        owner = await backend.first.admit(generation, attempt_id="owner")
        assert owner is not None
        if change == "attempt":
            forged = replace(owner, attempt_id="another-owner")
        elif change == "fence":
            forged = replace(owner, validation_fence="fabricated-fence")
        elif change == "generation":
            forged = replace(
                owner, generation=replace(generation, runtime_digest="sha256:" + "c" * 64)
            )
        else:
            forged = CredentialAdmission(generation, owner.attempt_id)
        assert not await backend.second.is_admitted(forged)
        assert await backend.second.complete_validation(forged) is None
        await backend.second.release(forged)
        assert await backend.first.is_admitted(owner)
        assert await backend.second.admit(generation, attempt_id="another") is None
        assert await backend.first.complete_validation(owner) is not None

    asyncio.run(scenario())
