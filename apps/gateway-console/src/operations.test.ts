import { describe, expect, it, vi } from "vitest";

import { OperationsApiClient, OperationsApiError } from "./api";
import { decodeDeployments, decodeOverview, OperationsResponseValidationError } from "./decoder";

const OVERVIEW = {
  registry: {
    schema_version: "1",
    catalog_version: "2026-09",
    source_date: "2026-09-08",
    digest: "sha256:registry",
    deployment_count: 1,
  },
  ranking: {
    schema_version: "1",
    policy_version: "ranking-v1",
    source_date: "2026-09-08",
    digest: "sha256:ranking",
    score_snapshot_id: "snapshot-1",
    score_provenance_mode: null,
    benchmark_snapshot_id: "benchmark-1",
    promotion_evidence_id: null,
    manual_override_id: null,
  },
  health: {
    scope: "process_local",
    deployment_count: 1,
    healthy: 1,
    degraded: 0,
    unhealthy: 0,
  },
  operational_evidence: { state: "available" },
};

const DEPLOYMENTS = {
  health_scope: "process_local",
  deployments: [
    {
      deployment_id: "openai-primary",
      provider: "openai",
      model_id: "gpt-example",
      model_group: "balanced",
      api_family: "responses",
      enabled: true,
      capabilities: ["structured_output"],
      modalities: ["text"],
      context_tokens: 128000,
      max_data_classification: "confidential",
      allowed_environments: ["dev"],
      pricing_snapshot_version: "pricing-1",
      health: { status: "healthy", circuit_state: "closed" },
    },
  ],
};

describe("Operations response decoders", () => {
  it("accepts the exact bounded overview contract", () => {
    expect(decodeOverview(OVERVIEW)).toEqual(OVERVIEW);
  });

  it("fails closed when overview contains an unexpected field", () => {
    expect(() => decodeOverview({ ...OVERVIEW, raw_provider_state: {} })).toThrow(
      OperationsResponseValidationError,
    );
  });

  it("fails closed when health counts contradict the registry", () => {
    expect(() =>
      decodeOverview({
        ...OVERVIEW,
        health: { ...OVERVIEW.health, healthy: 0 },
      }),
    ).toThrow("overview deployment counts are inconsistent");
  });

  it("accepts the bounded deployment catalog and process-local scope", () => {
    expect(decodeDeployments(DEPLOYMENTS)).toEqual(DEPLOYMENTS);
  });

  it("rejects runtime counters that are outside the PC-24 contract", () => {
    const deployment = { ...DEPLOYMENTS.deployments[0], request_count: 99 };
    expect(() => decodeDeployments({ ...DEPLOYMENTS, deployments: [deployment] })).toThrow(
      OperationsResponseValidationError,
    );
  });
});

describe("OperationsApiClient", () => {
  it("uses only GET requests with the explicit Gateway credential header", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(OVERVIEW))
      .mockResolvedValueOnce(jsonResponse(DEPLOYMENTS));
    const client = new OperationsApiClient(fetcher);

    await client.load("demo-key");

    expect(fetcher).toHaveBeenCalledTimes(2);
    for (const [path, init] of fetcher.mock.calls) {
      expect(path).toMatch(/^\/v1\/ops\/(overview|deployments)$/);
      expect(init.method).toBe("GET");
      expect(init.headers).toEqual({
        Accept: "application/json",
        "X-Gateway-API-Key": "demo-key",
      });
      expect(init.credentials).toBe("omit");
      expect(init.cache).toBe("no-store");
    }
  });

  it.each([
    [401, "invalid_gateway_credential", "invalid_credential"],
    [403, "operations_read_access_denied", "access_denied"],
    [503, "operations_snapshot_unavailable", "snapshot_unavailable"],
  ] as const)("maps sanitized HTTP %s without exposing raw detail", async (status, code, kind) => {
    const fetcher = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ detail: { code }, raw_exception: "must not be rendered" }, status)),
    );
    const client = new OperationsApiClient(fetcher);

    await expect(client.load("demo-key")).rejects.toMatchObject<Partial<OperationsApiError>>({ kind });
  });

  it("rejects cross-endpoint deployment count inconsistency", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(OVERVIEW))
      .mockResolvedValueOnce(jsonResponse({ ...DEPLOYMENTS, deployments: [] }));
    const client = new OperationsApiClient(fetcher);

    await expect(client.load("demo-key")).rejects.toMatchObject<Partial<OperationsApiError>>({
      kind: "invalid_response",
    });
  });
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
