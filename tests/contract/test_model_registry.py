import unittest
from pathlib import Path

from governed_llm_gateway_contracts import Capability, DataClassification, Modality
from governed_llm_gateway_core.adapters import load_model_registry, load_model_registry_text
from governed_llm_gateway_core.domain import DuplicateRegistryKeyError, ModelRegistryError

ROOT = Path(__file__).resolve().parents[2]


def registry_yaml(*, deployment_name: str = "alpha", vision: bool = False) -> str:
    vision_value = "true" if vision else "false"
    modalities = "[text, image]" if vision else "[text]"
    return f"""schema_version: "1.0"
catalog_version: "phase2"
source_date: "2026-08-31"
deployments:
  {deployment_name}:
    provider: test-provider
    model_id: vendor/model-a
    model_group: balanced
    api_family: openai-compatible
    capabilities:
      text: true
      vision: {vision_value}
      tool_calling: true
      structured_output: true
      streaming: true
    context_tokens: 128000
    modalities: {modalities}
    pricing:
      input_usd_per_million_tokens: "0.50"
      output_usd_per_million_tokens: "2.00"
      source_date: "2026-08-31"
      snapshot_version: "prices-1"
    max_data_classification: confidential
    allowed_environments: [benchmark, development]
    enabled: true
    source_date: "2026-08-31"
    catalog_version: "phase2"
"""


class ModelRegistryTests(unittest.TestCase):
    def test_checked_in_registry_is_valid_and_empty(self) -> None:
        registry = load_model_registry(ROOT / "config/model_registry.yaml")
        self.assertEqual(registry.schema_version, "1.0")
        self.assertEqual(registry.catalog_version, "phase2-empty")
        self.assertEqual(registry.deployments, ())
        self.assertEqual(len(registry.digest), 64)

    def test_loads_valid_registry(self) -> None:
        registry = load_model_registry_text(registry_yaml())
        deployment = registry.by_id("alpha")
        self.assertEqual(deployment.provider, "test-provider")
        self.assertEqual(
            deployment.max_data_classification,
            DataClassification.CONFIDENTIAL,
        )
        self.assertIn(Capability.TEXT, deployment.capabilities)
        self.assertEqual(deployment.modalities, frozenset({Modality.TEXT}))

    def test_missing_deployment_lookup_is_explicit(self) -> None:
        registry = load_model_registry_text(registry_yaml())
        with self.assertRaises(KeyError):
            registry.by_id("missing")

    def test_unknown_root_field_rejected(self) -> None:
        text = registry_yaml() + "unexpected: true\n"
        with self.assertRaisesRegex(ModelRegistryError, "unknown registry fields"):
            load_model_registry_text(text)

    def test_unknown_deployment_field_rejected(self) -> None:
        text = registry_yaml().replace(
            "    provider: test-provider\n",
            "    provider: test-provider\n    surprise: true\n",
        )
        with self.assertRaisesRegex(ModelRegistryError, "unknown deployment alpha fields"):
            load_model_registry_text(text)

    def test_duplicate_deployment_id_rejected(self) -> None:
        first = registry_yaml()
        duplicate = first + first[first.index("  alpha:\n") :]
        with self.assertRaises(DuplicateRegistryKeyError):
            load_model_registry_text(duplicate)

    def test_vision_and_image_must_match(self) -> None:
        text = registry_yaml().replace(
            "    modalities: [text]\n",
            "    modalities: [text, image]\n",
        )
        with self.assertRaisesRegex(
            ModelRegistryError,
            "vision capability and image modality",
        ):
            load_model_registry_text(text)

    def test_vision_registry_is_valid_when_both_signals_exist(self) -> None:
        deployment = load_model_registry_text(registry_yaml(vision=True)).by_id("alpha")
        self.assertIn(Capability.VISION, deployment.capabilities)
        self.assertIn(Modality.IMAGE, deployment.modalities)

    def test_text_capability_is_required(self) -> None:
        text = registry_yaml().replace("      text: true\n", "      text: false\n")
        with self.assertRaisesRegex(ModelRegistryError, "must declare text capability"):
            load_model_registry_text(text)

    def test_unknown_capability_rejected(self) -> None:
        text = registry_yaml().replace(
            "      streaming: true\n",
            "      streaming: true\n      audio: true\n",
        )
        with self.assertRaisesRegex(ModelRegistryError, "unknown alpha.capabilities fields"):
            load_model_registry_text(text)

    def test_deployment_catalog_must_match_registry(self) -> None:
        text = registry_yaml().replace(
            '    catalog_version: "phase2"\n',
            '    catalog_version: "other"\n',
        )
        with self.assertRaisesRegex(ModelRegistryError, "catalog_version must match"):
            load_model_registry_text(text)

    def test_deployment_source_date_must_match_registry(self) -> None:
        text = registry_yaml().replace(
            '    source_date: "2026-08-31"\n    catalog_version: "phase2"\n',
            '    source_date: "2026-08-30"\n    catalog_version: "phase2"\n',
        )
        with self.assertRaisesRegex(ModelRegistryError, "source_date must match"):
            load_model_registry_text(text)

    def test_digest_is_semantic_and_deterministic(self) -> None:
        first = registry_yaml()
        second = first.replace(
            "    allowed_environments: [benchmark, development]\n",
            "    allowed_environments: [development, benchmark]\n",
        )
        second = second.replace(
            '      input_usd_per_million_tokens: "0.50"\n',
            '      input_usd_per_million_tokens: "0.500"\n',
        )
        second = second.replace(
            "    modalities: [text]\n",
            "    modalities:\n      - text\n",
        )
        self.assertEqual(
            load_model_registry_text(first).digest,
            load_model_registry_text(second).digest,
        )

    def test_digest_changes_with_meaningful_content(self) -> None:
        first = load_model_registry_text(registry_yaml()).digest
        changed = registry_yaml().replace(
            "    context_tokens: 128000\n",
            "    context_tokens: 256000\n",
        )
        second = load_model_registry_text(changed).digest
        self.assertNotEqual(first, second)

    def test_unknown_pricing_is_explicitly_allowed(self) -> None:
        pricing = """    pricing:
      input_usd_per_million_tokens: "0.50"
      output_usd_per_million_tokens: "2.00"
      source_date: "2026-08-31"
      snapshot_version: "prices-1"
"""
        text = registry_yaml().replace(pricing, "    pricing: null\n")
        self.assertIsNone(load_model_registry_text(text).by_id("alpha").pricing)

    def test_safe_yaml_rejects_python_object_tags(self) -> None:
        text = "!!python/object/apply:os.system ['echo unsafe']"
        with self.assertRaises(ModelRegistryError):
            load_model_registry_text(text)

    def test_registry_root_must_be_mapping(self) -> None:
        with self.assertRaisesRegex(ModelRegistryError, "root must be a mapping"):
            load_model_registry_text("- not\n- a\n- registry\n")


if __name__ == "__main__":
    unittest.main()
