import { describe, expect, it } from "vitest";

import {
  DEPLOYMENT_CATALOG_COLUMNS,
  EMPTY_DEPLOYMENT_CATALOG_NOTICE,
  describeExcludedCandidates,
  describeExclusionReason,
} from "./catalog";
import type { InferenceRejectedCandidate } from "./inference";

describe("describeExcludedCandidates", () => {
  it("reports an empty list as unreported rather than as nothing excluded", () => {
    expect(describeExcludedCandidates([])).toBe("None reported");
  });

  it("renders one candidate as deployment, readable reason, and detail", () => {
    const candidates: InferenceRejectedCandidate[] = [
      { deployment: "openai-primary", reason: "context_too_small", detail: "needs 200k" },
    ];

    expect(describeExcludedCandidates(candidates)).toBe(
      "openai-primary: context window too small for the request (needs 200k)",
    );
  });

  it("omits the detail parenthesis when no detail was supplied", () => {
    const candidates: InferenceRejectedCandidate[] = [
      { deployment: "anthropic-primary", reason: "deployment_disabled", detail: null },
    ];

    expect(describeExcludedCandidates(candidates)).toBe(
      "anthropic-primary: disabled in the registry",
    );
  });

  it("preserves the order the routing evidence supplied", () => {
    const candidates: InferenceRejectedCandidate[] = [
      { deployment: "b", reason: "deployment_unhealthy", detail: null },
      { deployment: "a", reason: "circuit_breaker_open", detail: null },
    ];

    expect(describeExcludedCandidates(candidates)).toBe(
      "b: unhealthy at decision time · a: circuit breaker open at decision time",
    );
  });

  it("never claims a policy denial for a ranking-stage exclusion", () => {
    const candidates: InferenceRejectedCandidate[] = [
      { deployment: "openai-primary", reason: "wrong_model_group", detail: null },
    ];

    const rendered = describeExcludedCandidates(candidates).toLowerCase();

    expect(rendered).not.toContain("denied");
    expect(rendered).not.toContain("rejected");
  });
});

describe("describeExclusionReason", () => {
  it("passes an unknown reason token through unchanged", () => {
    expect(describeExclusionReason("reason_added_after_this_console")).toBe(
      "reason_added_after_this_console",
    );
  });

  it("keeps an empty detail string from producing an empty parenthesis", () => {
    const candidates: InferenceRejectedCandidate[] = [
      { deployment: "openai-primary", reason: "pricing_unavailable", detail: "" },
    ];

    expect(describeExcludedCandidates(candidates)).toBe(
      "openai-primary: no pricing evidence available",
    );
  });
});

describe("deployment catalog columns", () => {
  it("declares every header exactly once so the empty-state colspan stays honest", () => {
    expect(new Set(DEPLOYMENT_CATALOG_COLUMNS).size).toBe(DEPLOYMENT_CATALOG_COLUMNS.length);
    expect(DEPLOYMENT_CATALOG_COLUMNS.length).toBeGreaterThan(0);
  });

  it("keeps the empty-state notice from reading as a transport failure", () => {
    expect(EMPTY_DEPLOYMENT_CATALOG_NOTICE).toContain("an answer, not a failure");
    expect(EMPTY_DEPLOYMENT_CATALOG_NOTICE.toLowerCase()).not.toContain("error");
  });
});
