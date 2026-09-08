import { decodeDeployments, decodeOverview, OperationsResponseValidationError } from "./decoder";
import type { OperationsConsoleSnapshot } from "./types";

export type OperationsApiErrorKind =
  | "invalid_credential"
  | "access_denied"
  | "snapshot_unavailable"
  | "invalid_response"
  | "network_error"
  | "unexpected_http_error";

export class OperationsApiError extends Error {
  readonly kind: OperationsApiErrorKind;
  readonly status: number | null;

  constructor(kind: OperationsApiErrorKind, message: string, status: number | null = null) {
    super(message);
    this.name = "OperationsApiError";
    this.kind = kind;
    this.status = status;
  }
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class OperationsApiClient {
  readonly #fetch: FetchLike;

  constructor(fetcher: FetchLike = globalThis.fetch.bind(globalThis)) {
    this.#fetch = fetcher;
  }

  async load(apiKey: string, signal?: AbortSignal): Promise<OperationsConsoleSnapshot> {
    if (apiKey.trim().length === 0) {
      throw new OperationsApiError("invalid_credential", "Enter an Operations API key.");
    }

    const [overviewJson, deploymentsJson] = await Promise.all([
      this.#request("/v1/ops/overview", apiKey, signal),
      this.#request("/v1/ops/deployments", apiKey, signal),
    ]);

    try {
      const overview = decodeOverview(overviewJson);
      const deployments = decodeDeployments(deploymentsJson);
      if (
        overview.health.scope !== deployments.health_scope ||
        overview.registry.deployment_count !== deployments.deployments.length
      ) {
        throw new OperationsResponseValidationError("Operations responses are mutually inconsistent");
      }
      return { overview, deployments };
    } catch (error) {
      if (error instanceof OperationsResponseValidationError) {
        throw new OperationsApiError(
          "invalid_response",
          "Gateway returned Operations data that did not match the trusted contract.",
        );
      }
      throw error;
    }
  }

  async #request(path: string, apiKey: string, signal?: AbortSignal): Promise<unknown> {
    let response: Response;
    try {
      response = await this.#fetch(path, {
        method: "GET",
        headers: {
          Accept: "application/json",
          "X-Gateway-API-Key": apiKey,
        },
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
      throw new OperationsApiError(
        "network_error",
        "Gateway Operations API could not be reached.",
      );
    }

    if (!response.ok) {
      throw await mapHttpError(response);
    }

    try {
      return await response.json();
    } catch {
      throw new OperationsApiError(
        "invalid_response",
        "Gateway returned a non-JSON Operations response.",
        response.status,
      );
    }
  }
}

async function mapHttpError(response: Response): Promise<OperationsApiError> {
  const code = await readSanitizedErrorCode(response);
  if (response.status === 401 && code === "invalid_gateway_credential") {
    return new OperationsApiError("invalid_credential", "Gateway credential was rejected.", 401);
  }
  if (response.status === 403 && code === "operations_read_access_denied") {
    return new OperationsApiError(
      "access_denied",
      "This Gateway identity has no Operations read grant.",
      403,
    );
  }
  if (response.status === 503 && code === "operations_snapshot_unavailable") {
    return new OperationsApiError(
      "snapshot_unavailable",
      "Gateway Operations snapshot is currently unavailable.",
      503,
    );
  }
  return new OperationsApiError(
    "unexpected_http_error",
    `Gateway Operations request failed with HTTP ${response.status}.`,
    response.status,
  );
}

async function readSanitizedErrorCode(response: Response): Promise<string | null> {
  try {
    const payload: unknown = await response.json();
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      return null;
    }
    const detail = (payload as Record<string, unknown>).detail;
    if (typeof detail !== "object" || detail === null || Array.isArray(detail)) {
      return null;
    }
    const code = (detail as Record<string, unknown>).code;
    return typeof code === "string" ? code : null;
  } catch {
    return null;
  }
}
