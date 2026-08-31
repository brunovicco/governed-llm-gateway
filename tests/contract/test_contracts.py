import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import uuid4

from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    Message,
    MessageRole,
    RequestLimits,
    RiskLevel,
    WorkloadRequirements,
)


class ContractTests(unittest.TestCase):
    def make_request(self, workload: str = "agent.orchestration") -> GatewayRequest:
        return GatewayRequest(
            schema_version="1.0",
            request_id=uuid4(),
            workload=workload,
            risk_level=RiskLevel.MEDIUM,
            data_classification=DataClassification.PUBLIC,
            requirements=WorkloadRequirements(tool_calling=True, structured_output=True),
            limits=RequestLimits(max_latency_ms=15_000, max_cost_usd=Decimal("0.05")),
            messages=(Message(role=MessageRole.USER, content="hello"),),
        )

    def test_contract_is_frozen(self) -> None:
        request = self.make_request()
        with self.assertRaises(FrozenInstanceError):
            request.workload = "rag.answer"  # type: ignore[misc]

    def test_workload_is_policy_defined_dotted_identifier(self) -> None:
        self.assertEqual(self.make_request().workload, "agent.orchestration")
        with self.assertRaises(ValueError):
            self.make_request("agent")

    def test_negative_context_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            WorkloadRequirements(min_context_tokens=-1)

    def test_non_positive_latency_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RequestLimits(max_latency_ms=0)


if __name__ == "__main__":
    unittest.main()
