"""Deterministic structural code-generation workload contract and scorer."""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

CODE_GENERATION_CONTRACT_VERSION = "1.0"
CODE_GENERATION_SCORER_ID = "code_generation_ast_v1"
_FORBIDDEN_CALLS = frozenset({"eval", "exec", "compile", "open", "__import__"})
_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"asyncio", "httpx", "os", "pathlib", "requests", "shutil", "socket", "subprocess", "urllib"}
)


def load_code_generation_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate a Python structural-generation v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    for case in dataset.cases:
        validate_code_generation_case(case)
    return dataset


def validate_code_generation_case(case: BenchmarkCase) -> None:
    """Fail closed when a code-generation case drifts from the v1 contract."""
    if case.workload is not BenchmarkWorkload.CODE_GENERATION:
        raise ValueError("code generation dataset contains a different workload")
    if case.scorer != CODE_GENERATION_SCORER_ID:
        raise ValueError("code generation v1 requires its versioned deterministic scorer")
    if not isinstance(case.expected, str) or not case.expected.strip():
        raise ValueError("code generation expected output must be non-empty Python source")

    metadata = case.metadata
    if metadata.get("contract_version") != CODE_GENERATION_CONTRACT_VERSION:
        raise ValueError("code generation contract_version must be 1.0")
    if metadata.get("language") != "python":
        raise ValueError("code generation language must be python")
    if metadata.get("synthetic") is not True:
        raise ValueError("code generation cases must be explicitly synthetic")
    if metadata.get("comparison") != "ast_exact":
        raise ValueError("code generation comparison must be ast_exact")
    if metadata.get("execute_candidate") is not False:
        raise ValueError("code generation candidate execution must remain disabled")

    expected_tree = _parse_python(case.expected)
    _validate_safe_candidate(expected_tree)


def score_code_generation(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Compare reviewed and candidate Python structurally without executing either program."""
    validate_code_generation_case(case)
    if not isinstance(output, str) or not output.strip():
        return Decimal("0")

    try:
        candidate_tree = _parse_python(output)
        _validate_safe_candidate(candidate_tree)
    except (SyntaxError, ValueError):
        return Decimal("0")

    expected = case.expected
    if not isinstance(expected, str):
        raise AssertionError("validated code generation expected output must be Python source")
    expected_tree = _parse_python(expected)
    expected_dump = ast.dump(expected_tree, include_attributes=False)
    candidate_dump = ast.dump(candidate_tree, include_attributes=False)
    return Decimal("1") if candidate_dump == expected_dump else Decimal("0")


def _parse_python(source: str) -> ast.Module:
    return ast.parse(source, mode="exec")


def _validate_safe_candidate(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            roots = _import_roots(node)
            blocked = sorted(roots & _FORBIDDEN_IMPORT_ROOTS)
            if blocked:
                raise ValueError(f"code generation contains forbidden import: {blocked[0]}")
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in _FORBIDDEN_CALLS:
                raise ValueError(f"code generation contains forbidden call: {name}")


def _import_roots(node: ast.Import | ast.ImportFrom) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name.split(".", maxsplit=1)[0] for alias in node.names}
    if node.module is None:
        return set()
    return {node.module.split(".", maxsplit=1)[0]}


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
