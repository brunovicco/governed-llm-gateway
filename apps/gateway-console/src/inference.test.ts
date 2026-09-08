import { describe, expect, it, vi } from "vitest";

import { GovernedInferenceClient, InferenceApiError } from "./inference";

const ROUTING = {
  routing_decision_id: "route-1",
  policy: {
    decision_id: "policy-decision-1",
    policy_id: "gateway-generic",
    policy_version: "1.0",
    policy_digest: "sha256:policy",
  },
  authorized_model_group: "balanced",
  model_registry_digest: "sha256:registry",
  ranking_policy_version: "ranking-v1",
  ranking_policy_digest: "sha256:ranking",
  score_snapshot_id: "scores-1",
  benchmark_snapshot_id: null,
  score_provenance_mode: null,
  manual_override_id: null,
  provider: "google",
  model: "gemini-3.8-flash",
  deployment: "google-gemini-3-8-flash-dev",
  rejected_candidates: [],
  fallback_sequence: ["google-gemini-3-8-flash-dev"],
};

const USAGE = {
  input_tokens: 42,
  output_tokens: 11,
  total_tokens: 53,
};

const EXECUTION = {
  provider: "google",
  model: "gemini-3.8-flash",
  deployment: "google-gemini-3-8-flash-dev",
  status: "succeeded",
  latency_ms: 125,
  usage: USAGE,
  attempt_number: 1,
  fallback_index: 0,
  api_family: "generate-content",
  max_output_tokens: 256,
  finish_reason: "stop",
};

describe("GovernedInferenceClient", () => {
  it("posts only a provider-neutral bounded request and returns backend evidence", async () => {
    const fetcher = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestBody(init);
      return Promise.resolve(validResponse(request.request_id));
    });
    const client = new GovernedInferenceClient(fetcher);

    const result = await client.generate("demo-key", "What is deterministic routing?");

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [path, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/v1/generate");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("omit");
    expect(init.cache).toBe("no-store");
    expect(init.headers).toEqual({
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      "X-Gateway-API-Key": "demo-key",
    });

    const body = requestBody(init);
    expect(body.workload).toBe("rag.answer");
    expect(body.risk_level).toBe("low");
    expect(body.data_classification).toBe("public");
    expect(body).not.toHaveProperty("provider");
    expect(body).not.toHaveProperty("model");
    expect(body).not.toHaveProperty("deployment");

    expect(result.content).toBe("Deterministic routing keeps authority server-side.");
    expect(result.routing.authorized_model_group).toBe("balanced");
    expect(result.execution).toMatchObject({
      provider: "google",
      model: "gemini-3.8-flash",
      deployment: "google-gemini-3-8-flash-dev",
      status: "succeeded",
      latency_ms: 125,
    });
    expect(result.usage).toMatchObject({ input_tokens: 42, output_tokens: 11, total_tokens: 53 });
  });

  it("fails closed when the SSE request id differs from the submitted request", async () => {
    const client = new GovernedInferenceClient(
      vi.fn().mockResolvedValue(validResponse("00000000-0000-4000-8000-000000000000")),
    );

    await expect(client.generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "protocol_error" });
  });

  it("fails closed on a non-contiguous event sequence", async () => {
    const fetcher = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestBody(init);
      return Promise.resolve(
        sseResponse([
          event(request.request_id, 1, "response.started", { routing: ROUTING }),
          event(request.request_id, 3, "content.delta", { delta: "gap" }),
        ]),
      );
    });

    await expect(new GovernedInferenceClient(fetcher).generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "protocol_error" });
  });

  it("rejects duplicate normalized usage", async () => {
    const fetcher = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestBody(init);
      return Promise.resolve(
        sseResponse([
          event(request.request_id, 1, "response.started", { routing: ROUTING }),
          event(request.request_id, 2, "content.delta", { delta: "hello" }),
          event(request.request_id, 3, "usage.completed", { usage: USAGE }),
          event(request.request_id, 4, "usage.completed", { usage: USAGE }),
        ]),
      );
    });

    await expect(new GovernedInferenceClient(fetcher).generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "protocol_error" });
  });

  it("rejects contradictory routing and execution identities", async () => {
    const fetcher = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestBody(init);
      const execution = { ...EXECUTION, deployment: "unreviewed-deployment" };
      return Promise.resolve(
        sseResponse([
          event(request.request_id, 1, "response.started", { routing: ROUTING }),
          event(request.request_id, 2, "content.delta", { delta: "hello" }),
          event(request.request_id, 3, "usage.completed", { usage: USAGE }),
          event(request.request_id, 4, "response.completed", { routing: ROUTING, execution }),
        ]),
      );
    });

    await expect(new GovernedInferenceClient(fetcher).generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "protocol_error" });
  });

  it("rejects a stream that ends without terminal completion", async () => {
    const fetcher = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestBody(init);
      return Promise.resolve(
        sseResponse([
          event(request.request_id, 1, "response.started", { routing: ROUTING }),
          event(request.request_id, 2, "content.delta", { delta: "partial" }),
          event(request.request_id, 3, "usage.completed", { usage: USAGE }),
        ]),
      );
    });

    await expect(new GovernedInferenceClient(fetcher).generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "protocol_error" });
  });

  it("surfaces a normalized failed terminal event without raw provider detail", async () => {
    const fetcher = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestBody(init);
      return Promise.resolve(
        sseResponse([
          event(request.request_id, 1, "response.failed", {
            routing: ROUTING,
            error: { code: "provider_timeout", message: "raw provider message", retryable: false },
          }),
        ]),
      );
    });

    await expect(new GovernedInferenceClient(fetcher).generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "stream_failed", message: "Gateway inference failed (provider_timeout)." });
  });

  it("rejects tool events because the bounded demo request disables tool calling", async () => {
    const fetcher = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestBody(init);
      return Promise.resolve(
        sseResponse([
          event(request.request_id, 1, "response.started", { routing: ROUTING }),
          event(request.request_id, 2, "tool_call.started", {
            tool_call_id: "tool-1",
            tool_name: "unsafe",
          }),
        ]),
      );
    });

    await expect(new GovernedInferenceClient(fetcher).generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "protocol_error" });
  });

  it("rejects an SSE event that exceeds the reviewed byte limit", async () => {
    const fetcher = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      const request = requestBody(init);
      return Promise.resolve(
        sseResponse([
          event(request.request_id, 1, "response.started", { routing: ROUTING }),
          event(request.request_id, 2, "content.delta", { delta: "x".repeat(300_000) }),
        ]),
      );
    });

    await expect(new GovernedInferenceClient(fetcher).generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "protocol_error" });
  });

  it("maps a sanitized Policy Router denial", async () => {
    const client = new GovernedInferenceClient(
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: "policy_denied" }, raw: "do not render" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(client.generate("demo-key", "hello")).rejects.toMatchObject<
      Partial<InferenceApiError>
    >({ kind: "policy_denied", status: 403 });
  });
});

function validResponse(requestId: string): Response {
  return sseResponse([
    event(requestId, 1, "response.started", { routing: ROUTING }),
    event(requestId, 2, "content.delta", {
      delta: "Deterministic routing keeps authority server-side.",
    }),
    event(requestId, 3, "usage.completed", { usage: USAGE }),
    event(requestId, 4, "response.completed", { routing: ROUTING, execution: EXECUTION }),
  ]);
}

function event(
  requestId: string,
  sequenceNumber: number,
  eventType: string,
  extra: Record<string, unknown>,
): Record<string, unknown> {
  return {
    event_type: eventType,
    request_id: requestId,
    sequence_number: sequenceNumber,
    ...extra,
  };
}

function sseResponse(events: readonly Record<string, unknown>[]): Response {
  const body = events
    .map(
      (payload) =>
        `event: ${String(payload.event_type)}\nid: ${String(payload.sequence_number)}\ndata: ${JSON.stringify(payload)}\n\n`,
    )
    .join("");
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function requestBody(init?: RequestInit): Record<string, unknown> & { request_id: string } {
  if (typeof init?.body !== "string") {
    throw new Error("expected JSON request body");
  }
  const parsed = JSON.parse(init.body) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("expected JSON object request body");
  }
  const payload = parsed as Record<string, unknown>;
  if (typeof payload.request_id !== "string") {
    throw new Error("expected request_id");
  }
  return { ...payload, request_id: payload.request_id };
}
