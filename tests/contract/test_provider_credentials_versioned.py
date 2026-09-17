"""Synthetic adapter boundary checks, not backend/version authority conformance."""

import asyncio
import inspect
import traceback
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from typing import cast, get_type_hints

import pytest
from governed_llm_gateway_core.adapters.provider_credentials_versioned import (
    VersionedProviderCredential,
    VersionedProviderSecretError,
    VersionedProviderSecretErrorCode,
    VersionedProviderSecretResolver,
    resolve_exact_provider_credential,
)
from governed_llm_gateway_core.adapters.provider_runtime import (
    EnvironmentProviderSecretResolver,
)
from governed_llm_gateway_core.domain.credential_availability import (
    CredentialContractError,
    CredentialGeneration,
)

_MATERIAL = "synthetic-private-material-marker"
_VERSION = "synthetic-private-version-marker"
_BACKEND_DETAIL = "synthetic-backend-locator-and-error-marker"


def _generation() -> CredentialGeneration:
    return CredentialGeneration(
        binding_id="synthetic-private-binding-marker",
        epoch=7,
        material_id="synthetic-private-material-id-marker",
        secret_version_id=_VERSION,
        runtime_digest="sha256:" + "a" * 64,
        auth_scope_digest="sha256:" + "b" * 64,
    )


def _replace_metadata(value: CredentialGeneration, **changes: object) -> CredentialGeneration:
    apply_changes = cast(Callable[..., CredentialGeneration], replace)
    return apply_changes(value, **changes)


class _Resolver:
    """Deliberately injected result/error; no authority claim or external access."""

    def __init__(self, result: object, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[CredentialGeneration] = []

    async def resolve_version(
        self, generation: CredentialGeneration
    ) -> VersionedProviderCredential:
        self.calls.append(generation)
        if self.error is not None:
            raise self.error
        return cast(VersionedProviderCredential, self.result)


def test_exact_fetch_passes_the_captured_token_once_and_returns_its_result() -> None:
    generation = _generation()
    result = VersionedProviderCredential(generation, _MATERIAL)
    fixture = _Resolver(result)
    resolver: VersionedProviderSecretResolver = fixture

    resolved = asyncio.run(resolve_exact_provider_credential(generation, resolver))

    assert resolved is result
    assert resolved.credential == _MATERIAL
    assert fixture.calls == [generation]
    assert fixture.calls[0] is generation


def test_matching_metadata_is_not_a_material_authority_proof() -> None:
    generation = _generation()
    different_material = "another-synthetic-value"
    fixture = _Resolver(VersionedProviderCredential(generation, different_material))
    result = asyncio.run(resolve_exact_provider_credential(generation, fixture))
    assert result.credential == different_material
    assert result.generation == generation
    assert fixture.calls == [generation]


@pytest.mark.parametrize("epoch", [2**53 - 1, 2**53 + 1, 2**63 - 1])
def test_fetch_preserves_exact_integer_epochs(epoch: int) -> None:
    generation = replace(_generation(), epoch=epoch)
    fixture = _Resolver(VersionedProviderCredential(generation, _MATERIAL))
    result = asyncio.run(resolve_exact_provider_credential(generation, fixture))
    assert result.generation.epoch == epoch
    assert fixture.calls[0].epoch == epoch


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("binding_id", "other-binding"),
        ("epoch", 8),
        ("material_id", "other-material"),
        ("secret_version_id", "other-version"),
        ("runtime_digest", "sha256:" + "c" * 64),
        ("auth_scope_digest", "sha256:" + "d" * 64),
    ],
)
def test_fetch_rejects_every_mismatched_generation_dimension(field: str, value: object) -> None:
    generation = _generation()
    other = _replace_metadata(generation, **{field: value})
    fixture = _Resolver(VersionedProviderCredential(other, _MATERIAL))

    with pytest.raises(VersionedProviderSecretError) as caught:
        asyncio.run(resolve_exact_provider_credential(generation, fixture))

    assert caught.value.code is VersionedProviderSecretErrorCode.INVALID_RESULT
    assert fixture.calls == [generation]


@pytest.mark.parametrize("result", [None, _MATERIAL, {}, _generation(), object()])
def test_fetch_rejects_untyped_results_instead_of_minting_metadata(result: object) -> None:
    fixture = _Resolver(result)
    with pytest.raises(VersionedProviderSecretError) as caught:
        asyncio.run(resolve_exact_provider_credential(_generation(), fixture))
    assert caught.value.code is VersionedProviderSecretErrorCode.INVALID_RESULT
    assert len(fixture.calls) == 1


@pytest.mark.parametrize("generation", [None, {}, _VERSION, 7])
def test_invalid_request_is_rejected_before_any_resolver_call(generation: object) -> None:
    fixture = _Resolver(None)
    with pytest.raises(VersionedProviderSecretError) as caught:
        asyncio.run(
            resolve_exact_provider_credential(cast(CredentialGeneration, generation), fixture)
        )
    assert caught.value.code is VersionedProviderSecretErrorCode.INVALID_REQUEST
    assert fixture.calls == []


@pytest.mark.parametrize(
    "credential",
    [
        None,
        True,
        7,
        b"synthetic",
        "",
        " padded",
        "padded ",
        "a b",
        "a\t",
        "a\n",
        "a\x00",
        "a\x7f",
        "a\x85",
        "a\u00a0b",
    ],
)
def test_sensitive_result_rejects_malformed_material_without_echoing_it(credential: object) -> None:
    with pytest.raises(CredentialContractError) as caught:
        VersionedProviderCredential(_generation(), cast(str, credential))
    assert str(caught.value) == "versioned secret material is malformed"


def test_sensitive_result_requires_a_typed_generation() -> None:
    with pytest.raises(CredentialContractError):
        VersionedProviderCredential(cast(CredentialGeneration, _VERSION), _MATERIAL)


def test_sensitive_result_is_frozen_and_repr_and_hash_do_not_include_secret_or_token() -> None:
    generation = _generation()
    result = VersionedProviderCredential(generation, _MATERIAL)
    assert repr(result) == "VersionedProviderCredential()"
    assert str(result) == "VersionedProviderCredential()"
    assert result != VersionedProviderCredential(generation, _MATERIAL)
    assert type(result).__hash__ is object.__hash__
    assert hash(result) == object.__hash__(result)
    for attribute, replacement in (
        ("credential", "replacement"),
        ("generation", replace(generation, epoch=8)),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(result, attribute, replacement)
    assert not hasattr(result, "__dict__")


def test_fetch_revalidates_material_if_a_backend_violates_the_frozen_contract() -> None:
    result = VersionedProviderCredential(_generation(), _MATERIAL)
    object.__setattr__(result, "credential", "invalid\nmaterial")
    fixture = _Resolver(result)
    with pytest.raises(VersionedProviderSecretError) as caught:
        asyncio.run(resolve_exact_provider_credential(_generation(), fixture))
    assert caught.value.code is VersionedProviderSecretErrorCode.INVALID_RESULT
    assert caught.value.__suppress_context__
    assert len(fixture.calls) == 1


def test_backend_failure_is_sanitized_once_without_retry_or_raw_traceback_chaining(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _Resolver(None, RuntimeError(_BACKEND_DETAIL + _MATERIAL))
    with pytest.raises(VersionedProviderSecretError) as caught:
        asyncio.run(resolve_exact_provider_credential(_generation(), fixture))

    assert caught.value.code is VersionedProviderSecretErrorCode.UNAVAILABLE
    assert caught.value.args == ("versioned provider credential resolution failed",)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    rendered = "".join(traceback.format_exception(caught.value))
    for marker in (_MATERIAL, _VERSION, _BACKEND_DETAIL, _generation().binding_id):
        assert marker not in rendered
    assert len(fixture.calls) == 1
    assert caplog.records == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_task_cancellation_propagates_and_resolver_finally_owns_cleanup() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        cleaned = asyncio.Event()
        calls: list[CredentialGeneration] = []

        class BlockingResolver:
            async def resolve_version(
                self, generation: CredentialGeneration
            ) -> VersionedProviderCredential:
                calls.append(generation)
                try:
                    started.set()
                    await asyncio.Event().wait()
                    raise AssertionError("unreachable resolver completion")
                finally:
                    cleaned.set()

        generation = _generation()
        task = asyncio.create_task(
            resolve_exact_provider_credential(generation, BlockingResolver())
        )
        await asyncio.wait_for(started.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set()
        assert calls == [generation]

    asyncio.run(scenario())


def test_legacy_environment_resolver_is_not_an_exact_version_authority() -> None:
    legacy = EnvironmentProviderSecretResolver({"SYNTHETIC_API_KEY": _MATERIAL})
    with pytest.raises(VersionedProviderSecretError) as caught:
        asyncio.run(
            resolve_exact_provider_credential(
                _generation(), cast(VersionedProviderSecretResolver, legacy)
            )
        )
    assert caught.value.code is VersionedProviderSecretErrorCode.UNAVAILABLE
    assert legacy.resolve("SYNTHETIC_API_KEY") == _MATERIAL


@pytest.mark.parametrize("code", list(VersionedProviderSecretErrorCode))
def test_errors_accept_only_closed_metadata_and_have_fixed_private_safe_repr(
    code: VersionedProviderSecretErrorCode,
) -> None:
    error = VersionedProviderSecretError(code)
    assert error.code is code
    assert str(error) == "versioned provider credential resolution failed"
    assert _MATERIAL not in repr(error)
    with pytest.raises(CredentialContractError):
        VersionedProviderSecretError(cast(VersionedProviderSecretErrorCode, _BACKEND_DETAIL))


def test_async_port_has_no_publication_or_latest_resolution_capability() -> None:
    assert inspect.iscoroutinefunction(VersionedProviderSecretResolver.resolve_version)
    hints = get_type_hints(VersionedProviderSecretResolver.resolve_version)
    assert hints == {"generation": CredentialGeneration, "return": VersionedProviderCredential}
    for forbidden in ("resolve", "resolve_latest", "publish", "admit", "complete_validation"):
        assert not hasattr(VersionedProviderSecretResolver, forbidden)
