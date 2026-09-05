"""Deterministic agent-orchestration benchmark contract and scorer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

AGENT_ORCHESTRATION_BENCHMARK_VERSION = "agent-orchestration-v1"
AGENT_ORCHESTRATION_CONTRACT_VERSION = "1.0"
AGENT_ORCHESTRATION_SCORER_ID = "agent_orchestration_v1"

_ALLOWED_METADATA_FIELDS = {
    "allowed_actions",
    "allowed_agents",
    "contract_version",
    "execute_steps",
    "synthetic",
}
_STEP_FIELDS = {"action", "agent", "handoff_to"}

type _NormalizedStep = tuple[str, str, str | None]


@dataclass(frozen=True, slots=True, order=True)
class AgentOrchestrationIssue:
    """Stable reason code and JSON-pointer-like path for one trajectory issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class AgentOrchestrationAssessment:
    """Explainable sequence and handoff evidence for one proposed trajectory."""

    score: Decimal
    sequence_score: Decimal
    handoff_score: Decimal
    issues: tuple[AgentOrchestrationIssue, ...]

    @property
    def trajectory_success(self) -> bool:
        """Return whether the complete reviewed trajectory matched exactly."""
        return self.score == Decimal("1") and not self.issues


def load_agent_orchestration_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate a dataset containing only agent-orchestration v1 cases."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != AGENT_ORCHESTRATION_BENCHMARK_VERSION:
        raise ValueError("agent orchestration v1 requires benchmark_version agent-orchestration-v1")
    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("agent orchestration v1 case IDs must be unique")
    for case in dataset.cases:
        validate_agent_orchestration_case(case)
    return dataset


def validate_agent_orchestration_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 trajectory contract."""
    if case.workload is not BenchmarkWorkload.AGENT_ORCHESTRATION:
        raise ValueError("agent orchestration v1 dataset contains a different workload")
    if case.scorer != AGENT_ORCHESTRATION_SCORER_ID:
        raise ValueError("agent orchestration v1 requires its versioned deterministic scorer")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"agent orchestration v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != AGENT_ORCHESTRATION_CONTRACT_VERSION:
        raise ValueError("agent orchestration v1 contract_version must be 1.0")
    if metadata.get("synthetic") is not True:
        raise ValueError("agent orchestration v1 cases must be explicitly synthetic")
    if metadata.get("execute_steps") is not False:
        raise ValueError("agent orchestration v1 step execution must remain disabled")

    allowed_agents, actions_by_agent = _validated_allowlist(case)
    _validated_expected_steps(case.expected, allowed_agents, actions_by_agent)


def assess_agent_orchestration(
    case: BenchmarkCase,
    output: JsonValue,
) -> AgentOrchestrationAssessment:
    """Return deterministic sequence, handoff, and reason-code evidence."""
    validate_agent_orchestration_case(case)
    allowed_agents, actions_by_agent = _validated_allowlist(case)
    expected_steps = _validated_expected_steps(
        case.expected,
        allowed_agents,
        actions_by_agent,
    )
    output_steps, contract_issues = _normalized_output_steps(
        output,
        allowed_agents,
        actions_by_agent,
    )
    if output_steps is None:
        return _zero_assessment(contract_issues)

    denominator = max(len(expected_steps), len(output_steps), 1)
    common = min(len(expected_steps), len(output_steps))
    sequence_matches = 0
    handoff_matches = 0
    issues: list[AgentOrchestrationIssue] = []

    if len(expected_steps) != len(output_steps):
        issues.append(AgentOrchestrationIssue("step_count_mismatch", "/steps"))

    for index in range(common):
        expected_agent, expected_action, expected_handoff = expected_steps[index]
        output_agent, output_action, output_handoff = output_steps[index]
        step_path = f"/steps/{index}"

        if output_agent == expected_agent and output_action == expected_action:
            sequence_matches += 1
        else:
            if output_agent != expected_agent:
                issues.append(AgentOrchestrationIssue("wrong_agent", f"{step_path}/agent"))
            if output_action != expected_action:
                issues.append(AgentOrchestrationIssue("wrong_action", f"{step_path}/action"))

        if output_handoff == expected_handoff:
            handoff_matches += 1
        else:
            issues.append(AgentOrchestrationIssue("wrong_handoff", f"{step_path}/handoff_to"))

    for index in range(common, len(expected_steps)):
        issues.append(AgentOrchestrationIssue("missing_step", f"/steps/{index}"))
    for index in range(common, len(output_steps)):
        issues.append(AgentOrchestrationIssue("unexpected_step", f"/steps/{index}"))

    for index, (_, _, handoff_to) in enumerate(output_steps):
        if index < len(output_steps) - 1:
            next_agent = output_steps[index + 1][0]
            if handoff_to != next_agent:
                issues.append(
                    AgentOrchestrationIssue(
                        "broken_handoff_chain",
                        f"/steps/{index}/handoff_to",
                    )
                )
        elif handoff_to is not None:
            issues.append(
                AgentOrchestrationIssue(
                    "unterminated_trajectory",
                    f"/steps/{index}/handoff_to",
                )
            )

    sequence_score = Decimal(sequence_matches) / Decimal(denominator)
    handoff_score = Decimal(handoff_matches) / Decimal(denominator)
    score = (sequence_score + handoff_score) / Decimal("2")
    return AgentOrchestrationAssessment(
        score=score,
        sequence_score=sequence_score,
        handoff_score=handoff_score,
        issues=tuple(sorted(set(issues))),
    )


def score_agent_orchestration(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_agent_orchestration(case, output).score


def _validated_allowlist(
    case: BenchmarkCase,
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    agents_value = case.metadata.get("allowed_agents")
    if not isinstance(agents_value, list) or not agents_value:
        raise ValueError("agent orchestration v1 allowed_agents must be a non-empty string list")

    allowed_agents: list[str] = []
    for item in agents_value:
        if not isinstance(item, str) or not item or item.strip() != item:
            raise ValueError(
                "agent orchestration v1 allowed_agents must contain normalized strings"
            )
        allowed_agents.append(item)
    if len(allowed_agents) != len(set(allowed_agents)):
        raise ValueError("agent orchestration v1 allowed_agents must not contain duplicates")

    actions_value = case.metadata.get("allowed_actions")
    if not isinstance(actions_value, dict):
        raise ValueError("agent orchestration v1 allowed_actions must map every agent to actions")

    actions_by_agent: dict[str, tuple[str, ...]] = {}
    for agent, raw_actions in actions_value.items():
        if agent not in allowed_agents:
            raise ValueError("agent orchestration v1 allowed_actions contains an undeclared agent")
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ValueError(
                "agent orchestration v1 allowed_actions entries must be non-empty lists"
            )
        actions: list[str] = []
        for item in raw_actions:
            if not isinstance(item, str) or not item or item.strip() != item:
                raise ValueError(
                    "agent orchestration v1 allowed_actions must contain normalized strings"
                )
            actions.append(item)
        if len(actions) != len(set(actions)):
            raise ValueError("agent orchestration v1 allowed_actions must not contain duplicates")
        actions_by_agent[agent] = tuple(actions)

    if set(actions_by_agent) != set(allowed_agents):
        raise ValueError("agent orchestration v1 allowed_actions must cover every allowed agent")
    return tuple(allowed_agents), actions_by_agent


def _validated_expected_steps(
    expected: JsonValue,
    allowed_agents: tuple[str, ...],
    actions_by_agent: dict[str, tuple[str, ...]],
) -> tuple[_NormalizedStep, ...]:
    if not isinstance(expected, dict) or set(expected) != {"steps"}:
        raise ValueError("agent orchestration v1 expected output must contain exactly steps")
    raw_steps = expected.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("agent orchestration v1 expected steps must be a non-empty list")

    normalized: list[_NormalizedStep] = []
    for index, raw_step in enumerate(raw_steps):
        path = f"/steps/{index}"
        if not isinstance(raw_step, dict) or set(raw_step) != _STEP_FIELDS:
            raise ValueError(f"agent orchestration v1 expected step {path} has an invalid shape")
        agent = raw_step.get("agent")
        action = raw_step.get("action")
        handoff_to = raw_step.get("handoff_to")
        if not isinstance(agent, str) or not agent or agent.strip() != agent:
            raise ValueError(
                f"agent orchestration v1 expected step {path} agent must be normalized"
            )
        if agent not in allowed_agents:
            raise ValueError(
                f"agent orchestration v1 expected step {path} uses an undeclared agent"
            )
        if not isinstance(action, str) or not action or action.strip() != action:
            raise ValueError(
                f"agent orchestration v1 expected step {path} action must be normalized"
            )
        if action not in actions_by_agent[agent]:
            raise ValueError(
                f"agent orchestration v1 expected step {path} uses an undeclared action"
            )
        if handoff_to is not None:
            if (
                not isinstance(handoff_to, str)
                or not handoff_to
                or handoff_to.strip() != handoff_to
            ):
                raise ValueError(
                    f"agent orchestration v1 expected step {path} handoff must be normalized"
                )
            if handoff_to not in allowed_agents:
                raise ValueError(
                    f"agent orchestration v1 expected step {path} has an invalid handoff target"
                )
        normalized.append((agent, action, handoff_to))

    for index, (_, _, handoff_to) in enumerate(normalized):
        if index < len(normalized) - 1:
            if handoff_to != normalized[index + 1][0]:
                raise ValueError(
                    "agent orchestration v1 expected handoff chain must match the next agent"
                )
        elif handoff_to is not None:
            raise ValueError(
                "agent orchestration v1 expected trajectory must terminate with null handoff"
            )
    return tuple(normalized)


def _normalized_output_steps(
    output: JsonValue,
    allowed_agents: tuple[str, ...],
    actions_by_agent: dict[str, tuple[str, ...]],
) -> tuple[tuple[_NormalizedStep, ...] | None, tuple[AgentOrchestrationIssue, ...]]:
    if not isinstance(output, dict) or set(output) != {"steps"}:
        return None, (AgentOrchestrationIssue("invalid_output_shape", "/"),)

    raw_steps = output.get("steps")
    if not isinstance(raw_steps, list):
        return None, (AgentOrchestrationIssue("wrong_steps_type", "/steps"),)

    normalized: list[_NormalizedStep] = []
    issues: list[AgentOrchestrationIssue] = []
    for index, raw_step in enumerate(raw_steps):
        path = f"/steps/{index}"
        if not isinstance(raw_step, dict) or set(raw_step) != _STEP_FIELDS:
            issues.append(AgentOrchestrationIssue("invalid_step_shape", path))
            continue

        agent = raw_step.get("agent")
        action = raw_step.get("action")
        handoff_to = raw_step.get("handoff_to")
        valid = True

        if not isinstance(agent, str):
            issues.append(AgentOrchestrationIssue("wrong_agent_type", f"{path}/agent"))
            valid = False
        elif agent not in allowed_agents:
            issues.append(AgentOrchestrationIssue("undeclared_agent", f"{path}/agent"))
            valid = False

        if not isinstance(action, str):
            issues.append(AgentOrchestrationIssue("wrong_action_type", f"{path}/action"))
            valid = False
        elif isinstance(agent, str) and agent in actions_by_agent:
            if action not in actions_by_agent[agent]:
                issues.append(AgentOrchestrationIssue("undeclared_action", f"{path}/action"))
                valid = False

        if handoff_to is not None and not isinstance(handoff_to, str):
            issues.append(AgentOrchestrationIssue("wrong_handoff_type", f"{path}/handoff_to"))
            valid = False
        elif isinstance(handoff_to, str) and handoff_to not in allowed_agents:
            issues.append(AgentOrchestrationIssue("invalid_handoff_target", f"{path}/handoff_to"))
            valid = False

        if valid:
            if not isinstance(agent, str) or not isinstance(action, str):
                raise AssertionError("validated output step strings are inconsistent")
            if handoff_to is not None and not isinstance(handoff_to, str):
                raise AssertionError("validated output handoff is inconsistent")
            normalized.append((agent, action, handoff_to))

    if issues:
        return None, tuple(sorted(set(issues)))
    return tuple(normalized), ()


def _zero_assessment(
    issues: tuple[AgentOrchestrationIssue, ...],
) -> AgentOrchestrationAssessment:
    return AgentOrchestrationAssessment(
        score=Decimal("0"),
        sequence_score=Decimal("0"),
        handoff_score=Decimal("0"),
        issues=issues,
    )
