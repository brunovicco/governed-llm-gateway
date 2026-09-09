export type InferenceApiErrorKind =
  | "invalid_credential"
  | "invalid_request"
  | "policy_denied"
  | "execution_unavailable"
  | "stream_failed"
  | "protocol_error"
  | "network_error"
  | "unexpected_http_error";

export class InferenceApiError extends Error {
  readonly kind: InferenceApiErrorKind;
  readonly status: number | null;

  constructor(kind: InferenceApiErrorKind, message: string, status: number | null = null) {
    super(message);
    this.name = "InferenceApiError";
    this.kind = kind;
    this.status = status;
  }
}

export interface InferenceUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number | null;
  cache_read_input_tokens: number | null;
  cache_write_input_tokens: number | null;
  total_cost_usd: string | null;
}

export interface InferencePolicyProvenance {
  decision_id: string;
  policy_id: string;
  policy_version: string;
  policy_digest: string;
}

export interface InferenceRejectedCandidate {
  deployment: string;
  reason: string;
  detail: string | null;
}

export interface InferenceRouting {
  routing_decision_id: string;
  policy: InferencePolicyProvenance;
  authorized_model_group: string;
  model_registry_digest: string;
  ranking_policy_version: string;
  ranking_policy_digest: string | null;
  score_snapshot_id: string | null;
  benchmark_snapshot_id: string | null;
  score_provenance_mode: string | null;
  manual_override_id: string | null;
  provider: string;
  model: string;
  deployment: string;
  rejected_candidates: readonly InferenceRejectedCandidate[];
  fallback_sequence: readonly string[];
}

export interface InferenceExecution {
  provider: string;
  model: string;
  deployment: string;
  status: "succeeded";
  latency_ms: number;
  usage: InferenceUsage;
  attempt_number: number;
  fallback_index: number;
  api_family: string | null;
  max_output_tokens: number | null;
  finish_reason: string | null;
  trace_id: string | null;
}

export interface GovernedInferenceResult {
  request_id: string;
  content: string;
  routing: InferenceRouting;
  execution: InferenceExecution;
  usage: InferenceUsage;
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type StreamEventType =
  | "response.started"
  | "content.delta"
  | "tool_call.started"
  | "tool_call.arguments.delta"
  | "tool_call.completed"
  | "usage.completed"
  | "response.completed"
  | "response.failed";

interface StreamEvent {
  event_type: StreamEventType;
  request_id: string;
  sequence_number: number;
  routing: InferenceRouting | null;
  delta: string | null;
  usage: InferenceUsage | null;
  execution: InferenceExecution | null;
  error_code: string | null;
}

const MAX_PROMPT_CHARACTERS = 2_000;
const MAX_SSE_EVENT_BYTES = 256 * 1024;
const MAX_SSE_STREAM_BYTES = 2 * 1024 * 1024;
const ALLOWED_EVENT_TYPES = new Set<StreamEventType>([
  "response.started",
  "content.delta",
  "tool_call.started",
  "tool_call.arguments.delta",
  "tool_call.completed",
  "usage.completed",
  "response.completed",
  "response.failed",
]);
const EXPECTED_DEMO_EVENT_TYPES = new Set<StreamEventType>([
  "response.started",
  "content.delta",
  "usage.completed",
  "response.completed",
  "response.failed",
]);
const EVENT_FIELDS = new Set([
  "event_type",
  "request_id",
  "sequence_number",
  "routing",
  "delta",
  "tool_call_id",
  "tool_name",
  "tool_call",
  "usage",
  "execution",
  "finish_reason",
  "error",
  "partial",
]);
const ROUTING_FIELDS = new Set([
  "routing_decision_id",
  "policy",
  "authorized_model_group",
  "model_registry_digest",
  "ranking_policy_version",
  "ranking_policy_digest",
  "score_snapshot_id",
  "benchmark_snapshot_id",
  "score_provenance_mode",
  "manual_override_id",
  "provider",
  "model",
  "deployment",
  "rejected_candidates",
  "fallback_sequence",
]);
const POLICY_FIELDS = new Set(["decision_id", "policy_id", "policy_version", "policy_digest"]);
const REJECTION_FIELDS = new Set(["deployment", "reason", "detail"]);
const USAGE_FIELDS = new Set([
  "input_tokens",
  "output_tokens",
  "total_tokens",
  "cache_read_input_tokens",
  "cache_write_input_tokens",
  "total_cost_usd",
]);
const EXECUTION_FIELDS = new Set([
  "provider",
  "model",
  "deployment",
  "status",
  "latency_ms",
  "usage",
  "provider_request_id",
  "finish_reason",
  "attempt_number",
  "fallback_index",
  "api_family",
  "max_output_tokens",
  "trace_id",
]);
const ERROR_FIELDS = new Set(["code", "message", "retryable"]);
const TRACE_ID_PATTERN = /^[0-9a-f]{32}$/;

export class GovernedInferenceClient {
  readonly #fetch: FetchLike;

  constructor(fetcher: FetchLike = globalThis.fetch.bind(globalThis)) {
    this.#fetch = fetcher;
  }

  async generate(apiKey: string, prompt: string, signal?: AbortSignal): Promise<GovernedInferenceResult> {
    const normalizedApiKey = validateApiKey(apiKey);
    const normalizedPrompt = validatePrompt(prompt);
    const requestId = crypto.randomUUID();

    let response: Response;
    try {
      response = await this.#fetch("/v1/generate", {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
          "X-Gateway-API-Key": normalizedApiKey,
        },
        body: JSON.stringify(buildRequest(requestId, normalizedPrompt)),
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        referrerPolicy: "no-referrer",
        signal: signal ?? null,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      throw new InferenceApiError("network_error", "Gateway inference API could not be reached.");
    }

    if (!response.ok) {
      throw await mapHttpError(response);
    }

    const mediaType = (response.headers.get("content-type") ?? "")
      .split(";", 1)[0]
      ?.trim()
      .toLowerCase();
    if (mediaType !== "text/event-stream") {
      throw protocolError("Gateway inference response is not a trusted SSE stream.");
    }
    if (response.body === null) {
      throw protocolError("Gateway inference response is missing an SSE body.");
    }

    return consumeStream(response.body, requestId);
  }
}

function validateApiKey(value: string): string {
  if (value.length === 0 || value.trim().length === 0 || value.trim() !== value) {
    throw new InferenceApiError("invalid_credential", "Enter a normalized Gateway API key.");
  }
  return value;
}

function validatePrompt(value: string): string {
  const normalized = value.trim();
  if (normalized.length === 0) {
    throw new InferenceApiError("invalid_request", "Enter a prompt for the governed request.");
  }
  if (normalized.length > MAX_PROMPT_CHARACTERS) {
    throw new InferenceApiError(
      "invalid_request",
      `Prompt must be at most ${MAX_PROMPT_CHARACTERS} characters.`,
    );
  }
  return normalized;
}

function buildRequest(requestId: string, prompt: string): Record<string, unknown> {
  return {
    schema_version: "1.0",
    request_id: requestId,
    workload: "rag.answer",
    risk_level: "low",
    data_classification: "public",
    stream: true,
    requirements: {
      tool_calling: false,
      structured_output: false,
      vision: false,
      min_context_tokens: 0,
    },
    limits: {
      max_latency_ms: 60_000,
      max_cost_usd: "0.05",
    },
    messages: [{ role: "user", content: prompt }],
    context_tokens_estimated: 512,
    max_output_tokens: 256,
    provider_timeout_seconds: 30,
  };
}

async function consumeStream(
  body: ReadableStream<Uint8Array>,
  expectedRequestId: string,
): Promise<GovernedInferenceResult> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const encoder = new TextEncoder();
  let buffer = "";
  let totalBytes = 0;
  let expectedSequence = 1;
  let terminalSeen = false;
  let routing: InferenceRouting | null = null;
  let usage: InferenceUsage | null = null;
  let execution: InferenceExecution | null = null;
  const contentParts: string[] = [];

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        break;
      }
      if (value === undefined) {
        throw protocolError("Gateway inference stream returned an invalid byte chunk.");
      }
      totalBytes += value.byteLength;
      if (totalBytes > MAX_SSE_STREAM_BYTES) {
        throw protocolError("Gateway inference stream exceeded the reviewed size limit.");
      }
      buffer += decoder.decode(value, { stream: true });
      const processed = processFrames(
        buffer,
        encoder,
        expectedRequestId,
        expectedSequence,
        terminalSeen,
        routing,
        usage,
        execution,
        contentParts,
      );
      buffer = processed.buffer;
      expectedSequence = processed.expectedSequence;
      terminalSeen = processed.terminalSeen;
      routing = processed.routing;
      usage = processed.usage;
      execution = processed.execution;
      if (encoder.encode(buffer).byteLength > MAX_SSE_EVENT_BYTES) {
        throw protocolError("Gateway inference SSE event exceeded the reviewed size limit.");
      }
    }
  } catch (error) {
    if (error instanceof TypeError) {
      throw protocolError("Gateway inference stream is not valid UTF-8.");
    }
    throw error;
  } finally {
    reader.releaseLock();
  }

  const processed = processFrames(
    buffer,
    encoder,
    expectedRequestId,
    expectedSequence,
    terminalSeen,
    routing,
    usage,
    execution,
    contentParts,
  );
  buffer = processed.buffer;
  terminalSeen = processed.terminalSeen;
  routing = processed.routing;
  usage = processed.usage;
  execution = processed.execution;

  if (buffer.trim().length > 0) {
    throw protocolError("Gateway inference stream ended with an unterminated SSE event.");
  }
  if (!terminalSeen || routing === null || usage === null || execution === null) {
    throw protocolError("Gateway inference stream ended without complete terminal evidence.");
  }
  const content = contentParts.join("");
  if (content.length === 0) {
    throw protocolError("Gateway inference completed without response content.");
  }
  validateTerminalEvidence(routing, usage, execution);
  return {
    request_id: expectedRequestId,
    content,
    routing,
    execution,
    usage,
  };
}

interface ProcessedFrames {
  buffer: string;
  expectedSequence: number;
  terminalSeen: boolean;
  routing: InferenceRouting | null;
  usage: InferenceUsage | null;
  execution: InferenceExecution | null;
}

function processFrames(
  initialBuffer: string,
  encoder: TextEncoder,
  expectedRequestId: string,
  initialExpectedSequence: number,
  initialTerminalSeen: boolean,
  initialRouting: InferenceRouting | null,
  initialUsage: InferenceUsage | null,
  initialExecution: InferenceExecution | null,
  contentParts: string[],
): ProcessedFrames {
  let buffer = initialBuffer;
  let expectedSequence = initialExpectedSequence;
  let terminalSeen = initialTerminalSeen;
  let routing = initialRouting;
  let usage = initialUsage;
  let execution = initialExecution;

  while (true) {
    const extracted = extractFrame(buffer);
    if (extracted === null) {
      break;
    }
    buffer = extracted.rest;
    if (encoder.encode(extracted.frame).byteLength > MAX_SSE_EVENT_BYTES) {
      throw protocolError("Gateway inference SSE event exceeded the reviewed size limit.");
    }
    if (extracted.frame.trim().length === 0) {
      continue;
    }
    if (terminalSeen) {
      throw protocolError("Gateway inference emitted data after its terminal event.");
    }

    const parsed = parseFrame(extracted.frame);
    const event = decodeEvent(parsed.payload);
    if (parsed.eventName !== event.event_type) {
      throw protocolError("Gateway inference SSE event name does not match its payload.");
    }
    if (parsed.eventId !== event.sequence_number) {
      throw protocolError("Gateway inference SSE id does not match its payload sequence.");
    }
    if (event.request_id !== expectedRequestId) {
      throw protocolError("Gateway inference SSE request id does not match the submitted request.");
    }
    if (event.sequence_number !== expectedSequence) {
      throw protocolError("Gateway inference SSE sequence is not contiguous.");
    }
    expectedSequence += 1;

    if (!EXPECTED_DEMO_EVENT_TYPES.has(event.event_type)) {
      throw protocolError("Gateway emitted a tool event for a request with tool calling disabled.");
    }
    if (event.routing !== null) {
      if (routing !== null && !sameRoutingProvenance(routing, event.routing)) {
        throw protocolError("Gateway routing provenance changed during the inference stream.");
      }
      routing = event.routing;
    }

    if (event.event_type === "content.delta") {
      if (event.delta === null) {
        throw protocolError("Gateway content event is missing a text delta.");
      }
      contentParts.push(event.delta);
    } else if (event.event_type === "usage.completed") {
      if (event.usage === null) {
        throw protocolError("Gateway usage event is missing normalized usage.");
      }
      if (usage !== null) {
        throw protocolError("Gateway inference emitted normalized usage more than once.");
      }
      usage = event.usage;
    } else if (event.event_type === "response.failed") {
      terminalSeen = true;
      throw new InferenceApiError(
        "stream_failed",
        event.error_code === null
          ? "Gateway inference failed before trusted completion."
          : `Gateway inference failed (${event.error_code}).`,
      );
    } else if (event.event_type === "response.completed") {
      terminalSeen = true;
      if (event.routing === null || event.execution === null) {
        throw protocolError("Gateway completion is missing routing or execution evidence.");
      }
      execution = event.execution;
    }
  }

  return { buffer, expectedSequence, terminalSeen, routing, usage, execution };
}

function extractFrame(buffer: string): { frame: string; rest: string } | null {
  const delimiters = ["\r\n\r\n", "\n\n", "\r\r"] as const;
  let bestIndex = -1;
  let bestDelimiter = "";
  for (const delimiter of delimiters) {
    const index = buffer.indexOf(delimiter);
    if (index >= 0 && (bestIndex < 0 || index < bestIndex)) {
      bestIndex = index;
      bestDelimiter = delimiter;
    }
  }
  if (bestIndex < 0) {
    return null;
  }
  return {
    frame: buffer.slice(0, bestIndex),
    rest: buffer.slice(bestIndex + bestDelimiter.length),
  };
}

function parseFrame(frame: string): {
  eventName: string;
  eventId: number;
  payload: Record<string, unknown>;
} {
  let eventName: string | null = null;
  let eventIdText: string | null = null;
  const dataLines: string[] = [];

  for (const line of frame.split(/\r\n|\n|\r/)) {
    if (line.length === 0 || line.startsWith(":")) {
      continue;
    }
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    let value = separator < 0 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      if (eventName !== null) {
        throw protocolError("Gateway SSE event contains duplicate event fields.");
      }
      eventName = value;
    } else if (field === "id") {
      if (eventIdText !== null) {
        throw protocolError("Gateway SSE event contains duplicate id fields.");
      }
      eventIdText = value;
    } else if (field === "data") {
      dataLines.push(value);
    } else {
      throw protocolError(`Gateway SSE event contains unsupported field ${field || "<empty>"}.`);
    }
  }

  if (eventName === null || eventName.length === 0) {
    throw protocolError("Gateway SSE event is missing its event name.");
  }
  if (eventIdText === null || !/^[1-9][0-9]*$/.test(eventIdText)) {
    throw protocolError("Gateway SSE event id must be a positive integer.");
  }
  if (dataLines.length === 0) {
    throw protocolError("Gateway SSE event is missing data.");
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(dataLines.join("\n")) as unknown;
  } catch {
    throw protocolError("Gateway SSE event data is not valid JSON.");
  }
  return {
    eventName,
    eventId: Number(eventIdText),
    payload: asObject(parsed, "Gateway SSE event data"),
  };
}

function decodeEvent(payload: Record<string, unknown>): StreamEvent {
  checkFields(payload, EVENT_FIELDS, "Gateway stream event");
  const eventTypeValue = requiredString(payload, "event_type");
  if (!ALLOWED_EVENT_TYPES.has(eventTypeValue as StreamEventType)) {
    throw protocolError("Gateway stream event type is not part of the reviewed contract.");
  }
  const eventType = eventTypeValue as StreamEventType;
  const routingValue = payload.routing;
  const usageValue = payload.usage;
  const executionValue = payload.execution;
  const errorValue = payload.error;
  return {
    event_type: eventType,
    request_id: requiredString(payload, "request_id"),
    sequence_number: requiredInteger(payload, "sequence_number"),
    routing: routingValue === undefined ? null : decodeRouting(asObject(routingValue, "routing")),
    delta: optionalString(payload, "delta"),
    usage: usageValue === undefined ? null : decodeUsage(asObject(usageValue, "usage")),
    execution:
      executionValue === undefined ? null : decodeExecution(asObject(executionValue, "execution")),
    error_code:
      errorValue === undefined ? null : decodeErrorCode(asObject(errorValue, "gateway error")),
  };
}

function decodeRouting(payload: Record<string, unknown>): InferenceRouting {
  checkFields(payload, ROUTING_FIELDS, "routing provenance");
  const policy = asObject(payload.policy, "routing policy provenance");
  checkFields(policy, POLICY_FIELDS, "policy provenance");
  const provider = requiredString(payload, "provider");
  const model = requiredString(payload, "model");
  const deployment = requiredString(payload, "deployment");
  return {
    routing_decision_id: requiredString(payload, "routing_decision_id"),
    policy: {
      decision_id: requiredString(policy, "decision_id"),
      policy_id: requiredString(policy, "policy_id"),
      policy_version: requiredString(policy, "policy_version"),
      policy_digest: requiredString(policy, "policy_digest"),
    },
    authorized_model_group: requiredString(payload, "authorized_model_group"),
    model_registry_digest: requiredString(payload, "model_registry_digest"),
    ranking_policy_version: requiredString(payload, "ranking_policy_version"),
    ranking_policy_digest: optionalString(payload, "ranking_policy_digest"),
    score_snapshot_id: optionalString(payload, "score_snapshot_id"),
    benchmark_snapshot_id: optionalString(payload, "benchmark_snapshot_id"),
    score_provenance_mode: optionalString(payload, "score_provenance_mode"),
    manual_override_id: optionalString(payload, "manual_override_id"),
    provider,
    model,
    deployment,
    rejected_candidates: decodeRejectedCandidates(payload.rejected_candidates),
    fallback_sequence: decodeStringArray(payload.fallback_sequence, "fallback_sequence"),
  };
}

function decodeRejectedCandidates(value: unknown): readonly InferenceRejectedCandidate[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw protocolError("rejected_candidates must be a JSON array.");
  }
  return value.map((item) => {
    const payload = asObject(item, "rejected candidate");
    checkFields(payload, REJECTION_FIELDS, "rejected candidate");
    return {
      deployment: requiredString(payload, "deployment"),
      reason: requiredString(payload, "reason"),
      detail: optionalString(payload, "detail"),
    };
  });
}

function decodeUsage(payload: Record<string, unknown>): InferenceUsage {
  checkFields(payload, USAGE_FIELDS, "normalized usage");
  const cost = optionalString(payload, "total_cost_usd");
  if (cost !== null && !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(cost)) {
    throw protocolError("Normalized usage cost is not a decimal string.");
  }
  return {
    input_tokens: requiredNonNegativeInteger(payload, "input_tokens"),
    output_tokens: requiredNonNegativeInteger(payload, "output_tokens"),
    total_tokens: optionalNonNegativeInteger(payload, "total_tokens"),
    cache_read_input_tokens: optionalNonNegativeInteger(payload, "cache_read_input_tokens"),
    cache_write_input_tokens: optionalNonNegativeInteger(payload, "cache_write_input_tokens"),
    total_cost_usd: cost,
  };
}

function decodeExecution(payload: Record<string, unknown>): InferenceExecution {
  checkFields(payload, EXECUTION_FIELDS, "execution evidence");
  const status = requiredString(payload, "status");
  if (status !== "succeeded") {
    throw protocolError("Completed Gateway execution is not successful.");
  }
  const usageValue = payload.usage;
  if (usageValue === undefined) {
    throw protocolError("Completed Gateway execution is missing normalized usage.");
  }
  return {
    provider: requiredString(payload, "provider"),
    model: requiredString(payload, "model"),
    deployment: requiredString(payload, "deployment"),
    status,
    latency_ms: requiredNonNegativeInteger(payload, "latency_ms"),
    usage: decodeUsage(asObject(usageValue, "execution usage")),
    attempt_number: requiredPositiveInteger(payload, "attempt_number"),
    fallback_index: requiredNonNegativeInteger(payload, "fallback_index"),
    api_family: optionalString(payload, "api_family"),
    max_output_tokens: optionalPositiveInteger(payload, "max_output_tokens"),
    finish_reason: optionalString(payload, "finish_reason"),
    trace_id: decodeTraceId(payload),
  };
}

function decodeTraceId(payload: Record<string, unknown>): string | null {
  const value = optionalString(payload, "trace_id");
  if (value === null) {
    return null;
  }
  if (!TRACE_ID_PATTERN.test(value)) {
    throw protocolError("Execution evidence trace_id is not a 32-character lowercase hex string.");
  }
  return value;
}

function decodeErrorCode(payload: Record<string, unknown>): string {
  checkFields(payload, ERROR_FIELDS, "gateway error");
  const retryable = payload.retryable;
  if (typeof retryable !== "boolean") {
    throw protocolError("Gateway error retryable flag must be boolean.");
  }
  requiredString(payload, "message");
  return requiredString(payload, "code");
}

function validateTerminalEvidence(
  routing: InferenceRouting,
  usage: InferenceUsage,
  execution: InferenceExecution,
): void {
  if (
    routing.provider !== execution.provider ||
    routing.model !== execution.model ||
    routing.deployment !== execution.deployment
  ) {
    throw protocolError("Gateway routing and execution identities are contradictory.");
  }
  if (!sameUsage(usage, execution.usage)) {
    throw protocolError("Gateway execution usage does not match normalized stream usage.");
  }
  if (!routing.fallback_sequence.includes(execution.deployment)) {
    throw protocolError("Gateway execution deployment is absent from the reviewed fallback sequence.");
  }
  if (execution.fallback_index >= routing.fallback_sequence.length) {
    throw protocolError("Gateway execution fallback index is outside the reviewed fallback sequence.");
  }
  if (routing.fallback_sequence[execution.fallback_index] !== execution.deployment) {
    throw protocolError("Gateway execution fallback index contradicts the routing fallback sequence.");
  }
}

function sameRoutingProvenance(left: InferenceRouting, right: InferenceRouting): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function sameUsage(left: InferenceUsage, right: InferenceUsage): boolean {
  return (
    left.input_tokens === right.input_tokens &&
    left.output_tokens === right.output_tokens &&
    left.total_tokens === right.total_tokens &&
    left.cache_read_input_tokens === right.cache_read_input_tokens &&
    left.cache_write_input_tokens === right.cache_write_input_tokens &&
    left.total_cost_usd === right.total_cost_usd
  );
}

function checkFields(payload: Record<string, unknown>, allowed: ReadonlySet<string>, context: string): void {
  const unknown = Object.keys(payload).filter((key) => !allowed.has(key));
  if (unknown.length > 0) {
    throw protocolError(`${context} contains unsupported fields: ${unknown.sort().join(", ")}.`);
  }
}

function asObject(value: unknown, context: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw protocolError(`${context} must be a JSON object.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  if (typeof value !== "string" || value.length === 0) {
    throw protocolError(`${key} must be a non-empty string.`);
  }
  return value;
}

function optionalString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string" || value.length === 0) {
    throw protocolError(`${key} must be a non-empty string when supplied.`);
  }
  return value;
}

function requiredInteger(payload: Record<string, unknown>, key: string): number {
  const value = payload[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    throw protocolError(`${key} must be a safe integer.`);
  }
  return value;
}

function requiredNonNegativeInteger(payload: Record<string, unknown>, key: string): number {
  const value = requiredInteger(payload, key);
  if (value < 0) {
    throw protocolError(`${key} must be non-negative.`);
  }
  return value;
}

function requiredPositiveInteger(payload: Record<string, unknown>, key: string): number {
  const value = requiredInteger(payload, key);
  if (value <= 0) {
    throw protocolError(`${key} must be positive.`);
  }
  return value;
}

function optionalNonNegativeInteger(payload: Record<string, unknown>, key: string): number | null {
  if (payload[key] === undefined || payload[key] === null) {
    return null;
  }
  return requiredNonNegativeInteger(payload, key);
}

function optionalPositiveInteger(payload: Record<string, unknown>, key: string): number | null {
  if (payload[key] === undefined || payload[key] === null) {
    return null;
  }
  return requiredPositiveInteger(payload, key);
}

function decodeStringArray(value: unknown, context: string): readonly string[] {
  if (!Array.isArray(value)) {
    throw protocolError(`${context} must be a JSON array.`);
  }
  return value.map((item) => {
    if (typeof item !== "string" || item.length === 0) {
      throw protocolError(`${context} must contain non-empty strings.`);
    }
    return item;
  });
}

async function mapHttpError(response: Response): Promise<InferenceApiError> {
  const code = await readSanitizedErrorCode(response);
  if (response.status === 401 && code === "invalid_gateway_credential") {
    return new InferenceApiError("invalid_credential", "Gateway credential was rejected.", 401);
  }
  if (response.status === 403 && code === "policy_denied") {
    return new InferenceApiError(
      "policy_denied",
      "Policy Router denied this governed workload request.",
      403,
    );
  }
  if (
    response.status === 503 &&
    (code === "no_eligible_streaming_deployment" ||
      code === "ranking_policy_unavailable" ||
      code === "ranking_invariant_violation" ||
      code === "policy_router_unavailable")
  ) {
    return new InferenceApiError(
      "execution_unavailable",
      "No trusted governed execution path is currently available.",
      503,
    );
  }
  if (response.status === 422) {
    return new InferenceApiError(
      "invalid_request",
      "Gateway rejected the bounded inference request.",
      422,
    );
  }
  return new InferenceApiError(
    "unexpected_http_error",
    `Gateway inference request failed with HTTP ${response.status}.`,
    response.status,
  );
}

async function readSanitizedErrorCode(response: Response): Promise<string | null> {
  try {
    const payload = (await response.json()) as unknown;
    const root = asPlainObject(payload);
    const detail = root === null ? null : asPlainObject(root.detail);
    const code = detail?.code;
    return typeof code === "string" ? code : null;
  } catch {
    return null;
  }
}

function asPlainObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function protocolError(message: string): InferenceApiError {
  return new InferenceApiError("protocol_error", message);
}
