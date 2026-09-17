"""Internal credential metadata contracts, not distributed availability conformance."""

import inspect
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from typing import cast, get_type_hints

import pytest
from governed_llm_gateway_core.application.credential_availability import (
    CredentialAvailabilityError,
    CredentialAvailabilityErrorCode,
    CredentialAvailabilityPort,
    CredentialAvailabilityReadPort,
    CredentialGenerationPublisher,
)
from governed_llm_gateway_core.domain.credential_availability import (
    CredentialAdmission,
    CredentialAvailabilitySnapshot,
    CredentialAvailabilityState,
    CredentialBindingRejection,
    CredentialCompletionReceipt,
    CredentialContractError,
    CredentialGeneration,
    CredentialGenerationPublication,
    CredentialRejectionEvidence,
)

_VERSION_HANDLE = "version-private-marker"
_OTHER_VERSION_HANDLE = "other-version"


def _replace_metadata[T](value: T, **changes: object) -> T:
    """Exercise dynamically selected/invalid fixtures at the runtime-validation boundary."""
    apply_changes = cast(Callable[..., T], replace)
    return apply_changes(value, **changes)


def _generation() -> CredentialGeneration:
    return CredentialGeneration(
        binding_id="binding-private-marker",
        epoch=7,
        material_id="material-private-marker",
        secret_version_id=_VERSION_HANDLE,
        runtime_digest="sha256:" + "a" * 64,
        auth_scope_digest="sha256:" + "b" * 64,
    )


def _validation() -> CredentialAdmission:
    return CredentialAdmission(
        generation=_generation(),
        attempt_id="attempt-private-marker",
        validation_fence="validation-private-marker",
        validation_timeout_seconds=60.0,
    )


def _receipt() -> CredentialCompletionReceipt:
    return CredentialCompletionReceipt(
        generation=_generation(),
        attempt_id="attempt-private-marker",
        validation_fence="validation-private-marker",
        completion_fence="completion-private-marker",
    )


@pytest.mark.parametrize("field", ["binding_id", "material_id", "secret_version_id"])
@pytest.mark.parametrize("value", [None, 7, "", " padded", "a/b", "a:b", "a\n", "á", "x" * 129])
def test_generation_rejects_non_opaque_or_unbounded_metadata(field: str, value: object) -> None:
    with pytest.raises(CredentialContractError):
        _replace_metadata(_generation(), **{field: value})


@pytest.mark.parametrize("field", ["runtime_digest", "auth_scope_digest"])
@pytest.mark.parametrize("value", [None, "", "a" * 64, "sha256:" + "A" * 64, "sha256:" + "a" * 63])
def test_generation_requires_canonical_secret_free_provenance(field: str, value: object) -> None:
    with pytest.raises(CredentialContractError):
        _replace_metadata(_generation(), **{field: value})


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "7", 2**63])
def test_generation_requires_a_positive_bounded_integer_epoch(value: object) -> None:
    with pytest.raises(CredentialContractError):
        _replace_metadata(_generation(), epoch=value)


def test_generation_allows_metadata_boundaries_without_issuing_material_identity() -> None:
    generation = replace(_generation(), epoch=2**63 - 1, secret_version_id="x" * 128)
    assert generation.epoch == 2**63 - 1
    assert generation.material_id == _generation().material_id


@pytest.mark.parametrize(
    "field",
    [
        "binding_id",
        "epoch",
        "material_id",
        "secret_version_id",
        "runtime_digest",
        "auth_scope_digest",
    ],
)
def test_generation_equality_binds_every_captured_dimension(field: str) -> None:
    changes: dict[str, object] = {
        "binding_id": "other-binding",
        "epoch": 8,
        "material_id": "other-material",
        "secret_version_id": "other-version",
        "runtime_digest": "sha256:" + "c" * 64,
        "auth_scope_digest": "sha256:" + "d" * 64,
    }
    assert _replace_metadata(_generation(), **{field: changes[field]}) != _generation()


@pytest.mark.parametrize("state", list(CredentialAvailabilityState))
def test_snapshot_eligibility_is_narrowing_and_does_not_claim_validation(
    state: CredentialAvailabilityState,
) -> None:
    generation = _generation()
    snapshot = CredentialAvailabilitySnapshot(
        binding_id=generation.binding_id,
        state=state,
        generation=None if state is CredentialAvailabilityState.UNKNOWN else generation,
    )
    expected = state in {
        CredentialAvailabilityState.PENDING_VALIDATION,
        CredentialAvailabilityState.AVAILABLE,
    }
    for _ in range(3):
        assert snapshot.is_candidate_eligible(generation) is expected
    assert not snapshot.is_candidate_eligible(replace(generation, epoch=8))
    assert not snapshot.is_candidate_eligible(
        replace(generation, secret_version_id=_OTHER_VERSION_HANDLE)
    )
    assert snapshot.state is state


@pytest.mark.parametrize("state", list(CredentialAvailabilityState))
def test_snapshot_rejects_missing_or_contradictory_state(
    state: CredentialAvailabilityState,
) -> None:
    generation = _generation()
    with pytest.raises(CredentialContractError):
        CredentialAvailabilitySnapshot(
            binding_id=generation.binding_id,
            state=state,
            generation=generation if state is CredentialAvailabilityState.UNKNOWN else None,
        )


def test_snapshot_rejects_a_different_binding_or_unparsed_state() -> None:
    with pytest.raises(CredentialContractError):
        CredentialAvailabilitySnapshot(
            "different-binding", CredentialAvailabilityState.AVAILABLE, _generation()
        )
    with pytest.raises(CredentialContractError):
        CredentialAvailabilitySnapshot(
            _generation().binding_id,
            cast(CredentialAvailabilityState, "available"),
            _generation(),
        )


@pytest.mark.parametrize("epoch", [6, 7])
def test_publication_cannot_relabel_an_equal_or_older_epoch(epoch: int) -> None:
    with pytest.raises(CredentialContractError):
        CredentialGenerationPublication(replace(_generation(), epoch=epoch), _generation())


def test_publication_is_explicit_cas_and_allows_same_material_without_clearing_quarantine() -> None:
    previous = _generation()
    publication = CredentialGenerationPublication(replace(previous, epoch=8), previous)
    assert publication.expected_generation == previous
    assert publication.generation.material_id == previous.material_id
    assert CredentialGenerationPublication(previous).expected_generation is None
    with pytest.raises(CredentialContractError):
        CredentialGenerationPublication(replace(previous, binding_id="other-binding"), previous)


def test_ordinary_admission_has_no_validation_or_recovery_authority() -> None:
    admission = CredentialAdmission(_generation(), "ordinary-attempt")
    assert not admission.is_validation
    assert admission.validation_timeout_seconds is None
    assert not _receipt().matches_admission(admission)


@pytest.mark.parametrize(
    ("fence", "timeout"),
    [(None, 60.0), ("validation-fence", None), ("", 60.0)],
)
def test_validation_admission_requires_both_fence_and_explicit_lifetime(
    fence: str | None, timeout: float | None
) -> None:
    with pytest.raises(CredentialContractError):
        replace(_validation(), validation_fence=fence, validation_timeout_seconds=timeout)


@pytest.mark.parametrize("value", [True, "60", 0.0, -1.0, float("nan"), float("inf"), 10**400])
def test_validation_lifetime_must_be_numeric_finite_and_positive(value: object) -> None:
    with pytest.raises(CredentialContractError):
        _replace_metadata(_validation(), validation_timeout_seconds=value)


@pytest.mark.parametrize("field", ["attempt_id", "validation_fence"])
def test_admission_ownership_metadata_is_bounded(field: str) -> None:
    with pytest.raises(CredentialContractError):
        _replace_metadata(_validation(), **{field: "x" * 129})


def test_completion_receipt_correlates_the_exact_validation_owner_but_does_not_prove_liveness() -> (
    None
):
    receipt = _receipt()
    admission = _validation()
    assert admission.is_validation
    assert receipt.matches_admission(admission)
    assert not receipt.matches_admission(replace(admission, attempt_id="other-owner"))
    assert not receipt.matches_admission(replace(admission, validation_fence="other-fence"))
    assert not receipt.matches_admission(
        replace(admission, generation=replace(_generation(), epoch=8))
    )
    with pytest.raises(CredentialContractError):
        replace(receipt, completion_fence="")


@pytest.mark.parametrize("evidence", list(CredentialRejectionEvidence))
def test_rejection_fact_names_the_observed_generation_and_reviewed_classifier(
    evidence: CredentialRejectionEvidence,
) -> None:
    rejection = CredentialBindingRejection(_generation(), evidence, "classifier-private-marker")
    assert rejection.generation == _generation()
    assert rejection.evidence is evidence
    with pytest.raises(CredentialContractError):
        replace(rejection, classifier_id="")
    with pytest.raises(CredentialContractError):
        _replace_metadata(rejection, evidence=403)


def _values() -> tuple[
    CredentialGeneration
    | CredentialGenerationPublication
    | CredentialAvailabilitySnapshot
    | CredentialAdmission
    | CredentialCompletionReceipt
    | CredentialBindingRejection,
    ...,
]:
    generation = _generation()
    return (
        generation,
        CredentialGenerationPublication(replace(generation, epoch=8), generation),
        CredentialAvailabilitySnapshot(
            generation.binding_id, CredentialAvailabilityState.AVAILABLE, generation
        ),
        _validation(),
        _receipt(),
        CredentialBindingRejection(
            generation,
            CredentialRejectionEvidence.AUTHENTICATION_BOUNDARY_REJECTED,
            "classifier-private-marker",
        ),
    )


def test_nested_values_require_validated_generation_instances() -> None:
    for value in _values()[1:]:
        with pytest.raises(CredentialContractError):
            _replace_metadata(value, generation=None)
    with pytest.raises(CredentialContractError):
        CredentialGenerationPublication(_generation(), cast(CredentialGeneration, "invalid"))


def test_contracts_are_frozen_and_repr_hides_internal_identity_and_version_metadata() -> None:
    rendered = repr(_values())
    for marker in (
        "binding-private-marker",
        "material-private-marker",
        "version-private-marker",
        "attempt-private-marker",
        "validation-private-marker",
        "completion-private-marker",
        "classifier-private-marker",
        _generation().runtime_digest,
        _generation().auth_scope_digest,
    ):
        assert marker not in rendered
    for value in _values():
        with pytest.raises(FrozenInstanceError):
            setattr(value, fields(value)[0].name, "replacement")


@pytest.mark.parametrize(
    "field", ["binding_id", "material_id", "secret_version_id", "runtime_digest"]
)
def test_contract_errors_do_not_echo_invalid_private_input(field: str) -> None:
    marker = "private-input-must-not-appear/invalid"
    with pytest.raises(CredentialContractError) as error:
        _replace_metadata(_generation(), **{field: marker})
    assert marker not in str(error.value)
    assert marker not in repr(error.value)


@pytest.mark.parametrize("code", list(CredentialAvailabilityErrorCode))
def test_control_errors_are_closed_and_sanitized(code: CredentialAvailabilityErrorCode) -> None:
    error = CredentialAvailabilityError(code)
    assert error.code is code
    assert str(error) == "credential availability control failed"
    with pytest.raises(CredentialContractError):
        CredentialAvailabilityError(cast(CredentialAvailabilityErrorCode, "raw-backend-detail"))


def test_ports_separate_read_worker_and_publisher_contracts_without_implementing_a_backend() -> (
    None
):
    assert (
        get_type_hints(CredentialAvailabilityReadPort.snapshot)["return"]
        is CredentialAvailabilitySnapshot
    )
    assert not hasattr(CredentialAvailabilityReadPort, "admit")
    assert not hasattr(CredentialAvailabilityPort, "publish")
    assert not hasattr(CredentialGenerationPublisher, "admit")
    for name in (
        "snapshot",
        "admit",
        "is_admitted",
        "release",
        "complete_validation",
        "is_completion_current",
        "record_rejection",
    ):
        assert inspect.iscoroutinefunction(getattr(CredentialAvailabilityPort, name))
    attempt = inspect.signature(CredentialAvailabilityPort.admit).parameters["attempt_id"]
    assert attempt.kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.iscoroutinefunction(CredentialGenerationPublisher.publish)
