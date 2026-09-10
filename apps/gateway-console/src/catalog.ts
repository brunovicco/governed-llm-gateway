import type { InferenceRejectedCandidate } from "./inference";

/**
 * Column headers of the deployment catalog table.
 *
 * The table renders its header cells from this list and spans its empty-state
 * row across `DEPLOYMENT_CATALOG_COLUMNS.length`, so the two cannot drift.
 */
export const DEPLOYMENT_CATALOG_COLUMNS: readonly string[] = [
  "Deployment",
  "Provider / model",
  "Group",
  "Capabilities",
  "Context",
  "Environment",
  "Health",
];

/**
 * Empty catalog copy.
 *
 * Zero rows is a legitimate answer from the operations read model, not a
 * transport failure: the console already renders a distinct error state when
 * the request itself fails.
 */
export const EMPTY_DEPLOYMENT_CATALOG_NOTICE =
  "No deployment is visible under this credential. An empty catalog is an answer, not a failure: " +
  "the operations read model returned zero deployments for the authorized scope.";

/**
 * Human-readable text for the ranking-stage exclusion reasons the gateway emits.
 *
 * Every reason here is applied after the policy boundary has already authorized
 * the candidate set, so none of them means "denied by policy".
 */
const EXCLUSION_REASON_TEXT: Readonly<Record<string, string>> = {
  wrong_model_group: "outside the authorized model group",
  deployment_disabled: "disabled in the registry",
  missing_capability: "missing a required capability",
  context_too_small: "context window too small for the request",
  provider_not_authorized: "provider not authorized for this request",
  pricing_unavailable: "no pricing evidence available",
  ranking_score_unavailable: "no ranking score available",
  deployment_unhealthy: "unhealthy at decision time",
  circuit_breaker_open: "circuit breaker open at decision time",
  cost_limit_exceeded: "estimated cost above the request limit",
  latency_limit_exceeded: "expected latency above the request limit",
};

/** Return readable text for one exclusion reason, preserving unknown tokens verbatim. */
export function describeExclusionReason(reason: string): string {
  return EXCLUSION_REASON_TEXT[reason] ?? reason;
}

/**
 * Summarize the candidates that ranking dropped before selection.
 *
 * An empty list is reported as "None reported" rather than "None": the console
 * can only state what the routing evidence carried, not that nothing was dropped.
 */
export function describeExcludedCandidates(
  candidates: readonly InferenceRejectedCandidate[],
): string {
  if (candidates.length === 0) {
    return "None reported";
  }
  return candidates
    .map((candidate) => {
      const reason = describeExclusionReason(candidate.reason);
      const detail = candidate.detail;
      return detail === null || detail === ""
        ? `${candidate.deployment}: ${reason}`
        : `${candidate.deployment}: ${reason} (${detail})`;
    })
    .join(" · ");
}
