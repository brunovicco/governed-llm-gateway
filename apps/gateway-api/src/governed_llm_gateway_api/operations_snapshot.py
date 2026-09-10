"""Deployment-owned binding for the read-only Operations snapshot source."""

from dataclasses import dataclass

from governed_llm_gateway_core.application import OperationsReadModelService, OperationsSnapshot
from governed_llm_gateway_core.domain.operational_evidence import OperationalEvidenceSnapshot


@dataclass(frozen=True, slots=True)
class DeploymentOperationsSnapshotReader:
    """Bind one validated evidence artifact to the process Operations read model."""

    read_model: OperationsReadModelService
    operational_evidence: OperationalEvidenceSnapshot | None = None

    def __post_init__(self) -> None:
        """Reject unvalidated runtime objects without reading config, secrets, or the network."""
        if not isinstance(self.read_model, OperationsReadModelService):
            raise TypeError("read_model must use OperationsReadModelService")
        if self.operational_evidence is not None and not isinstance(
            self.operational_evidence,
            OperationalEvidenceSnapshot,
        ):
            raise TypeError("operational_evidence must use OperationalEvidenceSnapshot or None")

    async def snapshot(self) -> OperationsSnapshot:
        """Read current process state with the exact startup-bound evidence snapshot."""
        return await self.read_model.snapshot(operational_evidence=self.operational_evidence)
