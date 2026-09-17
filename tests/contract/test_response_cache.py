"""A cache that serves a stored completion must not become an authorization shortcut."""

import hashlib
import json
import unittest
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import fakeredis.aioredis
from governed_llm_gateway_contracts import (
    DataClassification,
    ImageInput,
    ImageMediaType,
    Message,
    MessageRole,
    RiskLevel,
)
from governed_llm_gateway_core.adapters.response_cache_redis import RedisResponseCache
from governed_llm_gateway_core.application.response_cache import CachedResponse
from governed_llm_gateway_core.domain.response_cache import (
    CACHE_SCHEMA_VERSION,
    ResponseCacheIdentity,
    ResponseCachePolicy,
    ResponseCachePolicyError,
    is_cacheable_request,
    messages_digest,
)

REQUEST_ID = UUID("66666666-6666-4666-8666-666666666666")
MESSAGES = (Message(role=MessageRole.USER, content="explain deterministic routing"),)


def _identity(**overrides: object) -> ResponseCacheIdentity:
    fields: dict[str, object] = {
        "client_id": "client-a",
        "policy_digest": "sha256:" + "f" * 64,
        "workload": "rag.answer",
        "risk_level": RiskLevel.LOW,
        "data_classification": DataClassification.PUBLIC,
        "authorized_model_group": "balanced",
        "model_registry_digest": "a" * 64,
        "ranking_policy_digest": "b" * 64,
        "max_output_tokens": 2000,
        "messages_digest": messages_digest(MESSAGES),
    }
    fields.update(overrides)
    factory = cast(Callable[..., ResponseCacheIdentity], ResponseCacheIdentity)
    return factory(**fields)


def _response() -> CachedResponse:
    return CachedResponse(
        content="deterministic routing picks one authorized deployment",
        input_tokens=11,
        output_tokens=8,
        provider="nvidia",
        model="nvidia/nemotron-3-super-120b-a12b",
        deployment="nvidia-nemotron-3-super-dev",
        api_family="openai-compatible",
        finish_reason="stop",
        cached_at=datetime.now(UTC),
        source_request_id=REQUEST_ID,
    )


class PolicyTests(unittest.TestCase):
    def test_caching_is_off_by_default(self) -> None:
        policy = ResponseCachePolicy()

        self.assertFalse(
            policy.permits(workload="rag.answer", data_classification=DataClassification.PUBLIC)
        )

    def test_an_enabled_policy_must_name_its_workloads(self) -> None:
        with self.assertRaises(ResponseCachePolicyError):
            ResponseCachePolicy(enabled=True)

    def test_only_the_named_workloads_are_cached(self) -> None:
        policy = ResponseCachePolicy(enabled=True, allowed_workloads=frozenset({"rag.answer"}))

        self.assertTrue(
            policy.permits(workload="rag.answer", data_classification=DataClassification.PUBLIC)
        )
        self.assertFalse(
            policy.permits(
                workload="reasoning.complex", data_classification=DataClassification.PUBLIC
            )
        )

    def test_public_is_a_ceiling_no_configuration_can_raise(self) -> None:
        """Anything above public would leave the process as stored prompt-derived material."""
        policy = ResponseCachePolicy(enabled=True, allowed_workloads=frozenset({"rag.answer"}))

        for classification in (
            DataClassification.INTERNAL,
            DataClassification.CONFIDENTIAL,
            DataClassification.RESTRICTED,
        ):
            with self.subTest(classification=classification):
                self.assertFalse(
                    policy.permits(workload="rag.answer", data_classification=classification)
                )

    def test_an_unbounded_lifetime_is_refused(self) -> None:
        for ttl in (0, -1, 86_401):
            with self.subTest(ttl=ttl), self.assertRaises(ResponseCachePolicyError):
                ResponseCachePolicy(
                    enabled=True, allowed_workloads=frozenset({"rag.answer"}), ttl_seconds=ttl
                )


class CacheIdentityTests(unittest.TestCase):
    def test_the_same_authorized_context_produces_the_same_key(self) -> None:
        self.assertEqual(_identity().digest, _identity().digest)

    def test_every_authorization_binding_changes_the_key(self) -> None:
        """An entry produced under one authority must be unreachable from another."""
        baseline = _identity().digest
        variations = {
            "client_id": "client-b",
            "policy_digest": "sha256:" + "e" * 64,
            "workload": "reasoning.complex",
            "risk_level": RiskLevel.HIGH,
            "data_classification": DataClassification.INTERNAL,
            "authorized_model_group": "reasoning-strong",
            "model_registry_digest": "c" * 64,
            "ranking_policy_digest": "d" * 64,
            "max_output_tokens": 4000,
            "messages_digest": messages_digest(
                (Message(role=MessageRole.USER, content="a different question"),)
            ),
        }
        for field, value in variations.items():
            with self.subTest(field=field):
                self.assertNotEqual(baseline, _identity(**{field: value}).digest)

    def test_a_registry_change_invalidates_stored_answers(self) -> None:
        """A different registry may route elsewhere, so a pre-change answer is not current."""
        self.assertNotEqual(_identity().digest, _identity(model_registry_digest="e" * 64).digest)

    def test_message_role_participates_in_the_digest(self) -> None:
        as_user = messages_digest((Message(role=MessageRole.USER, content="same text"),))
        as_system = messages_digest((Message(role=MessageRole.SYSTEM, content="same text"),))

        self.assertNotEqual(as_user, as_system)

    def test_missing_or_malformed_client_identity_is_not_a_shared_default(self) -> None:
        for value in (None, 7, "", " padded", "a b", "a/b", "á", "x" * 129):
            with self.subTest(value=value), self.assertRaises(ResponseCachePolicyError) as caught:
                _identity(client_id=value)
            self.assertEqual(
                str(caught.exception), "client_id must be a normalized bounded identifier"
            )

    def test_pdp_policy_digest_must_be_canonical(self) -> None:
        for value in (None, 7, "", "f" * 64, "sha256:" + "F" * 64, "sha256:" + "f" * 63):
            with self.subTest(value=value), self.assertRaises(ResponseCachePolicyError) as caught:
                _identity(policy_digest=value)
            self.assertEqual(str(caught.exception), "policy_digest must be a canonical PDP digest")

    def test_client_id_is_not_exposed_in_default_repr(self) -> None:
        self.assertNotIn(
            "client-private-marker", repr(_identity(client_id="client-private-marker"))
        )

    def test_version_two_does_not_reuse_the_legacy_identity_digest(self) -> None:
        legacy = {
            "schema_version": "1.0",
            "workload": "rag.answer",
            "risk_level": "low",
            "data_classification": "public",
            "authorized_model_group": "balanced",
            "model_registry_digest": "a" * 64,
            "ranking_policy_digest": "b" * 64,
            "max_output_tokens": 2000,
            "messages_digest": messages_digest(MESSAGES),
        }
        canonical = json.dumps(legacy, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        legacy_digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(CACHE_SCHEMA_VERSION, "2.0")
        self.assertNotEqual(_identity().digest, legacy_digest)


class CacheableShapeTests(unittest.TestCase):
    def test_plain_text_is_cacheable(self) -> None:
        self.assertTrue(
            is_cacheable_request(MESSAGES, structured_output_requested=False, tools_requested=False)
        )

    def test_tool_and_structured_requests_are_not_cached(self) -> None:
        self.assertFalse(
            is_cacheable_request(MESSAGES, structured_output_requested=True, tools_requested=False)
        )
        self.assertFalse(
            is_cacheable_request(MESSAGES, structured_output_requested=False, tools_requested=True)
        )

    def test_image_input_is_not_cached_because_it_is_not_in_the_digest(self) -> None:
        with_image = (
            Message(
                role=MessageRole.USER,
                content="describe this",
                images=(
                    ImageInput(media_type=ImageMediaType.PNG, url="https://example.test/a.png"),
                ),
            ),
        )

        self.assertFalse(
            is_cacheable_request(
                with_image, structured_output_requested=False, tools_requested=False
            )
        )


class RedisResponseCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.cache = RedisResponseCache(self.client, prefix="test")
        self.addAsyncCleanup(self.client.aclose)

    async def test_a_miss_returns_none(self) -> None:
        self.assertIsNone(await self.cache.get(_identity()))

    async def test_a_stored_completion_round_trips_with_its_execution_identity(self) -> None:
        stored = _response()

        await self.cache.put(_identity(), stored, ttl_seconds=60)
        loaded = await self.cache.get(_identity())

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.content, stored.content)
        self.assertEqual(loaded.deployment, stored.deployment)
        self.assertEqual(loaded.provider, stored.provider)
        self.assertEqual(loaded.source_request_id, REQUEST_ID)

    async def test_a_different_authorized_context_never_reads_the_entry(self) -> None:
        await self.cache.put(_identity(), _response(), ttl_seconds=60)

        self.assertIsNone(
            await self.cache.get(_identity(authorized_model_group="reasoning-strong"))
        )
        self.assertIsNone(await self.cache.get(_identity(workload="reasoning.complex")))

    async def test_clients_and_pdp_policies_do_not_read_each_others_entries(self) -> None:
        await self.cache.put(_identity(), _response(), ttl_seconds=60)
        self.assertIsNone(await self.cache.get(_identity(client_id="client-b")))
        self.assertIsNone(await self.cache.get(_identity(policy_digest="sha256:" + "e" * 64)))
        self.assertIsNotNone(await self.cache.get(_identity()))

    async def test_entries_always_carry_an_expiry(self) -> None:
        identity = _identity()

        await self.cache.put(identity, _response(), ttl_seconds=45)

        self.assertEqual(await self.client.ttl(self.cache.cache_key(identity)), 45)

    async def test_an_unbounded_lifetime_is_refused_at_the_adapter_too(self) -> None:
        with self.assertRaises(ValueError):
            await self.cache.put(_identity(), _response(), ttl_seconds=0)

    async def test_the_stored_key_never_contains_the_prompt(self) -> None:
        identity = _identity()

        await self.cache.put(identity, _response(), ttl_seconds=60)

        key = self.cache.cache_key(identity)
        self.assertNotIn("deterministic routing", key)
        self.assertNotIn("rag.answer", key)
        self.assertNotIn(identity.client_id, key)
        self.assertTrue(key.startswith("test:cache:2.0:"))

    async def test_a_corrupt_entry_is_a_miss_not_a_crash(self) -> None:
        identity = _identity()
        await self.client.set(self.cache.cache_key(identity), "{not json")

        self.assertIsNone(await self.cache.get(identity))

    async def test_an_entry_from_another_schema_version_is_a_miss(self) -> None:
        identity = _identity()
        await self.client.set(
            self.cache.cache_key(identity),
            '{"schema_version": "0.9", "content": "stale shape"}',
        )

        self.assertIsNone(await self.cache.get(identity))

    async def test_legacy_payload_copied_to_the_new_key_is_not_accepted(self) -> None:
        identity = _identity()
        await self.cache.put(identity, _response(), ttl_seconds=60)
        raw = await self.client.get(self.cache.cache_key(identity))
        assert raw is not None
        payload = json.loads(raw)
        payload["schema_version"] = "1.0"
        await self.client.set(self.cache.cache_key(identity), json.dumps(payload), ex=60)
        self.assertIsNone(await self.cache.get(identity))

    async def test_new_reader_never_falls_back_to_the_unversioned_keyspace(self) -> None:
        identity = _identity()
        legacy_key = "test:cache:" + identity.digest.removeprefix("sha256:")
        await self.cache.put(identity, _response(), ttl_seconds=60)
        raw = await self.client.get(self.cache.cache_key(identity))
        assert raw is not None
        await self.client.set(legacy_key, raw, ex=60)
        await self.client.delete(self.cache.cache_key(identity))
        self.assertIsNone(await self.cache.get(identity))
        self.assertIsNotNone(
            await self.client.get(legacy_key), "migration does not delete old data"
        )

    async def test_two_deployments_sharing_a_server_do_not_read_each_other(self) -> None:
        other = RedisResponseCache(self.client, prefix="other")
        await self.cache.put(_identity(), _response(), ttl_seconds=60)

        self.assertIsNone(await other.get(_identity()))


if __name__ == "__main__":
    unittest.main()
