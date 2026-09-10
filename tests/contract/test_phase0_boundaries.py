import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def imports_under(path: Path) -> set[str]:
    roots: set[str] = set()
    for file in path.rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
    return roots


class BoundaryTests(unittest.TestCase):
    def test_contracts_have_no_runtime_framework_dependencies(self) -> None:
        imports = imports_under(ROOT / "packages/gateway-contracts/src")
        forbidden = {"openai", "anthropic", "fastapi", "httpx", "opentelemetry", "sqlalchemy"}
        self.assertFalse(imports & forbidden)

    def test_application_depends_on_no_telemetry_backend(self) -> None:
        """The application owns telemetry vocabulary; adapters own the backend binding."""
        imports = imports_under(
            ROOT / "packages/gateway-core/src/governed_llm_gateway_core/application"
        )
        forbidden = {
            "a2a_otel_kit",
            "anthropic",
            "fastapi",
            "openai",
            "opentelemetry",
            "redis",
            "sqlalchemy",
        }

        self.assertFalse(imports & forbidden)

    def test_the_observability_binding_is_reachable_from_exactly_one_adapter(self) -> None:
        """A second binding would mean the port stopped being the only seam."""
        core = ROOT / "packages/gateway-core/src/governed_llm_gateway_core"
        binding_files = sorted(
            path.relative_to(core).as_posix()
            for path in core.rglob("*.py")
            if "a2a_otel_kit" in imports_under(path.parent)
            and "a2a_otel_kit" in path.read_text(encoding="utf-8")
        )

        self.assertEqual(
            binding_files,
            [
                "adapters/http_json.py",
                "adapters/http_sse.py",
                "adapters/observability_otel.py",
            ],
        )

    def test_domain_has_no_provider_or_http_framework_dependencies(self) -> None:
        imports = imports_under(ROOT / "packages/gateway-core/src/governed_llm_gateway_core/domain")
        forbidden = {
            "openai",
            "anthropic",
            "fastapi",
            "httpx",
            "opentelemetry",
            "sqlalchemy",
            "redis",
        }
        self.assertFalse(imports & forbidden)


if __name__ == "__main__":
    unittest.main()
