"""Static architecture boundary validator for the gateway workspace."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_CONTRACT_PREFIXES = {
    "anthropic",
    "fastapi",
    "google",
    "httpx",
    "openai",
    "opentelemetry",
    "sqlalchemy",
}
FORBIDDEN_DOMAIN_PREFIXES = FORBIDDEN_CONTRACT_PREFIXES | {"redis"}

BOUNDARIES = {
    ROOT / "packages/gateway-contracts/src/governed_llm_gateway_contracts": (
        FORBIDDEN_CONTRACT_PREFIXES
    ),
    ROOT / "packages/gateway-core/src/governed_llm_gateway_core/domain": FORBIDDEN_DOMAIN_PREFIXES,
}


def imported_roots(path: Path) -> set[str]:
    """Return top-level module names imported by one Python file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
        ):
            roots.add("__dynamic_import__")
    return roots


def main() -> int:
    """Validate provider/framework dependency boundaries."""

    violations: list[str] = []
    for boundary, forbidden in BOUNDARIES.items():
        for path in sorted(boundary.rglob("*.py")):
            imports = imported_roots(path)
            blocked = imports & forbidden
            if "__dynamic_import__" in imports:
                blocked.add("dynamic import")
            if blocked:
                relative = path.relative_to(ROOT)
                violations.append(f"{relative}: forbidden imports: {sorted(blocked)}")

    gateway_files = list((ROOT / "packages").rglob("*.py")) + list((ROOT / "apps").rglob("*.py"))
    business_roots = {
        "opslens",
        "ragforge",
        "getnet_multi_agent_support_v2",
        "controlled_autonomy_lab",
        "multi_agent_credit_desk",
        "verifiable_ai_governance",
    }
    for path in gateway_files:
        blocked = imported_roots(path) & business_roots
        if blocked:
            relative = path.relative_to(ROOT)
            violations.append(f"{relative}: consumer dependency forbidden: {sorted(blocked)}")

    if violations:
        print("Architecture boundary violations:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("architecture_check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
