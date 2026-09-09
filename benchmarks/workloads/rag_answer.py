"""Deterministic grounded RAG-answer benchmark contract and scorer."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

RAG_ANSWER_BENCHMARK_VERSION = "rag-answer-v1"
RAG_ANSWER_CONTRACT_VERSION = "1.0"
RAG_ANSWER_SCORER_ID = "rag_answer_v1"
RAG_ANSWER_RESPONSE_FORMAT = "grounded_answer_v1"

_ALLOWED_METADATA_FIELDS = {
    "contract_version",
    "forbidden_claims",
    "language",
    "question",
    "required_facts",
    "response_format",
    "sources",
    "synthetic",
}
_EXPECTED_CASE_COUNT = 6
_EXPECTED_LANGUAGES = {"en", "pt-BR"}
_OUTPUT_FIELDS = {"answer", "citations"}
_SOURCE_FIELDS = {"source_id", "text"}
_PROMPT_PREFIX = (
    "Answer using only the reviewed synthetic sources below. Return only JSON with exactly "
    "answer and citations, where citations is a list of source_id values. Do not cite any "
    "source not shown. Question: "
)


@dataclass(frozen=True, slots=True, order=True)
class RagAnswerIssue:
    """Stable reason code and JSON-pointer-like path for one grounded-answer issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class RagAnswerAssessment:
    """Explainable deterministic evidence for one grounded answer."""

    score: Decimal
    fact_score: Decimal
    citation_score: Decimal
    issues: tuple[RagAnswerIssue, ...]

    @property
    def grounded_success(self) -> bool:
        """Return whether facts and citations match the reviewed evidence exactly."""
        return self.score == Decimal("1") and not self.issues


def load_rag_answer_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate the complete reviewed rag-answer-v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != RAG_ANSWER_BENCHMARK_VERSION:
        raise ValueError("rag answer v1 requires benchmark_version rag-answer-v1")

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("rag answer v1 case IDs must be unique")
    if len(dataset.cases) != _EXPECTED_CASE_COUNT:
        raise ValueError("rag answer v1 requires exactly six reviewed cases")

    languages: set[str] = set()
    for case in dataset.cases:
        validate_rag_answer_case(case)
        language = case.metadata["language"]
        if not isinstance(language, str):
            raise AssertionError("validated rag answer language is inconsistent")
        languages.add(language)

    if languages != _EXPECTED_LANGUAGES:
        raise ValueError("rag answer v1 must cover exactly en and pt-BR")
    return dataset


def validate_rag_answer_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 grounding contract."""
    if case.workload is not BenchmarkWorkload.RAG_ANSWER:
        raise ValueError("rag answer v1 dataset contains a different workload")
    if case.scorer != RAG_ANSWER_SCORER_ID:
        raise ValueError("rag answer v1 requires its versioned deterministic scorer")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"rag answer v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != RAG_ANSWER_CONTRACT_VERSION:
        raise ValueError("rag answer v1 contract_version must be 1.0")
    if metadata.get("response_format") != RAG_ANSWER_RESPONSE_FORMAT:
        raise ValueError("rag answer v1 response_format must be grounded_answer_v1")
    if metadata.get("synthetic") is not True:
        raise ValueError("rag answer v1 cases must be explicitly synthetic")

    language = metadata.get("language")
    if language not in _EXPECTED_LANGUAGES:
        raise ValueError("rag answer v1 language must be en or pt-BR")

    question = _normalized_string(metadata.get("question"), "question")
    sources = _validated_sources(metadata.get("sources"))
    required_facts = _normalized_string_list(
        metadata.get("required_facts"),
        label="required_facts",
        require_nonempty=True,
    )
    forbidden_claims = _normalized_string_list(
        metadata.get("forbidden_claims", []),
        label="forbidden_claims",
        require_nonempty=False,
    )

    expected_answer, expected_citations = _validated_expected(case.expected, sources)
    normalized_expected_answer = expected_answer.casefold()
    missing_facts = [
        fact for fact in required_facts if fact.casefold() not in normalized_expected_answer
    ]
    if missing_facts:
        raise ValueError("rag answer v1 reference answer must contain every required fact")
    if any(claim.casefold() in normalized_expected_answer for claim in forbidden_claims):
        raise ValueError("rag answer v1 reference answer must not contain forbidden claims")

    cited_source_ids = set(expected_citations)
    cited_source_text = "\n".join(
        text for source_id, text in sources if source_id in cited_source_ids
    ).casefold()
    unsupported_facts = [
        fact for fact in required_facts if fact.casefold() not in cited_source_text
    ]
    if unsupported_facts:
        raise ValueError("rag answer v1 expected citations must support every required fact")

    expected_prompt = _build_prompt(question, sources)
    if case.prompt != expected_prompt:
        raise ValueError("rag answer v1 prompt must exactly materialize reviewed sources")

    if not expected_citations:
        raise ValueError("rag answer v1 expected citations must be non-empty")


def assess_rag_answer(case: BenchmarkCase, output: JsonValue) -> RagAnswerAssessment:
    """Return deterministic fact-coverage and citation-grounding evidence."""
    validate_rag_answer_case(case)
    sources = _validated_sources(case.metadata["sources"])
    required_facts = _normalized_string_list(
        case.metadata["required_facts"],
        label="required_facts",
        require_nonempty=True,
    )
    forbidden_claims = _normalized_string_list(
        case.metadata.get("forbidden_claims", []),
        label="forbidden_claims",
        require_nonempty=False,
    )
    _, expected_citations = _validated_expected(case.expected, sources)

    normalized_output, output_issues = _normalized_output(output, sources)
    if normalized_output is None:
        return _zero_assessment(output_issues)

    answer, citations = normalized_output
    normalized_answer = answer.casefold()
    forbidden_matches = [
        index
        for index, claim in enumerate(forbidden_claims)
        if claim.casefold() in normalized_answer
    ]
    if forbidden_matches:
        forbidden_issues = tuple(
            RagAnswerIssue("unsupported_claim", f"/answer/forbidden_claims/{index}")
            for index in forbidden_matches
        )
        return _zero_assessment(forbidden_issues)

    fact_matches = 0
    issues: list[RagAnswerIssue] = []
    for index, fact in enumerate(required_facts):
        if fact.casefold() in normalized_answer:
            fact_matches += 1
        else:
            issues.append(
                RagAnswerIssue("missing_required_fact", f"/answer/required_facts/{index}")
            )
    fact_score = Decimal(fact_matches) / Decimal(len(required_facts))

    citation_score, citation_issues = _citation_score(expected_citations, citations)
    issues.extend(citation_issues)
    score = (fact_score + citation_score) / Decimal("2")
    return RagAnswerAssessment(
        score=score,
        fact_score=fact_score,
        citation_score=citation_score,
        issues=tuple(sorted(set(issues))),
    )


def score_rag_answer(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_rag_answer(case, output).score


def _validated_sources(value: JsonValue) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError("rag answer v1 sources must contain at least two reviewed records")

    sources: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != _SOURCE_FIELDS:
            raise ValueError(
                f"rag answer v1 source {index} must contain exactly source_id and text"
            )
        source_id = _normalized_string(item.get("source_id"), f"sources[{index}].source_id")
        text = _normalized_string(item.get("text"), f"sources[{index}].text")
        sources.append((source_id, text))

    source_ids = [source_id for source_id, _ in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("rag answer v1 source IDs must be unique per case")
    return tuple(sources)


def _validated_expected(
    value: JsonValue,
    sources: Sequence[tuple[str, str]],
) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, dict) or set(value) != _OUTPUT_FIELDS:
        raise ValueError("rag answer v1 expected output must contain exactly answer and citations")
    answer = _normalized_string(value.get("answer"), "expected.answer")
    citations = _normalized_string_list(
        value.get("citations"),
        label="expected.citations",
        require_nonempty=True,
    )
    known_source_ids = {source_id for source_id, _ in sources}
    if not set(citations) <= known_source_ids:
        raise ValueError("rag answer v1 expected citations must reference reviewed sources")
    return answer, tuple(citations)


def _normalized_output(
    output: JsonValue,
    sources: Sequence[tuple[str, str]],
) -> tuple[tuple[str, tuple[str, ...]] | None, tuple[RagAnswerIssue, ...]]:
    if not isinstance(output, dict) or set(output) != _OUTPUT_FIELDS:
        return None, (RagAnswerIssue("invalid_output_shape", "/"),)

    answer = output.get("answer")
    citations = output.get("citations")
    if not isinstance(answer, str) or not answer.strip():
        return None, (RagAnswerIssue("invalid_answer", "/answer"),)
    if (
        not isinstance(citations, list)
        or not citations
        or not all(
            isinstance(citation, str) and citation and citation.strip() == citation
            for citation in citations
        )
    ):
        return None, (RagAnswerIssue("invalid_citations", "/citations"),)

    normalized_citations = [citation for citation in citations if isinstance(citation, str)]
    if len(normalized_citations) != len(set(normalized_citations)):
        return None, (RagAnswerIssue("duplicate_citation", "/citations"),)

    known_source_ids = {source_id for source_id, _ in sources}
    unknown = [
        (index, citation)
        for index, citation in enumerate(normalized_citations)
        if citation not in known_source_ids
    ]
    if unknown:
        issues = tuple(
            RagAnswerIssue("unknown_citation", f"/citations/{index}") for index, _ in unknown
        )
        return None, issues

    return (answer, tuple(normalized_citations)), ()


def _citation_score(
    expected: Sequence[str],
    observed: Sequence[str],
) -> tuple[Decimal, tuple[RagAnswerIssue, ...]]:
    expected_set = set(expected)
    observed_set = set(observed)
    matches = expected_set & observed_set
    precision = Decimal(len(matches)) / Decimal(len(observed_set))
    recall = Decimal(len(matches)) / Decimal(len(expected_set))
    if precision + recall == 0:
        score = Decimal("0")
    else:
        score = (Decimal("2") * precision * recall) / (precision + recall)

    issues: list[RagAnswerIssue] = []
    for source_id in sorted(expected_set - observed_set):
        issues.append(RagAnswerIssue("missing_supporting_citation", f"/citations/{source_id}"))
    for source_id in sorted(observed_set - expected_set):
        issues.append(RagAnswerIssue("unexpected_citation", f"/citations/{source_id}"))
    return score, tuple(issues)


def _normalized_string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"rag answer v1 {label} must be a normalized non-empty string")
    return value


def _normalized_string_list(
    value: JsonValue,
    *,
    label: str,
    require_nonempty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, list) or (require_nonempty and not value):
        qualifier = "non-empty " if require_nonempty else ""
        raise ValueError(f"rag answer v1 {label} must be a {qualifier}string list")
    if not all(isinstance(item, str) and item and item.strip() == item for item in value):
        raise ValueError(f"rag answer v1 {label} must contain normalized strings")
    items = tuple(item for item in value if isinstance(item, str))
    if len(items) != len(set(items)):
        raise ValueError(f"rag answer v1 {label} must not contain duplicates")
    return items


def _build_prompt(question: str, sources: Sequence[tuple[str, str]]) -> str:
    source_text = "\n".join(f"[{source_id}] {text}" for source_id, text in sources)
    return f"{_PROMPT_PREFIX}{question}\nSources:\n{source_text}"


def _zero_assessment(issues: Sequence[RagAnswerIssue]) -> RagAnswerAssessment:
    return RagAnswerAssessment(
        score=Decimal("0"),
        fact_score=Decimal("0"),
        citation_score=Decimal("0"),
        issues=tuple(sorted(set(issues))),
    )
