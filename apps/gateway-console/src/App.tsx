import { type FormEvent, useRef, useState } from "react";

import { OperationsApiClient, OperationsApiError } from "./api";
import {
  GovernedInferenceClient,
  type GovernedInferenceResult,
  InferenceApiError,
} from "./inference";
import { buildLocalGrafanaDashboardUrl, buildLocalGrafanaTraceUrl } from "./observability";
import type { OperationsConsoleSnapshot, OperationsDeployment } from "./types";

const operationsClient = new OperationsApiClient();
const inferenceClient = new GovernedInferenceClient();
const DEFAULT_PROMPT = "Explain in one sentence what deterministic model routing means.";

type ConnectionState =
  | { kind: "disconnected" }
  | { kind: "loading" }
  | { kind: "connected"; snapshot: OperationsConsoleSnapshot }
  | { kind: "error"; message: string };

type InferenceState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "succeeded"; result: GovernedInferenceResult }
  | { kind: "error"; message: string };

export function App() {
  const [apiKey, setApiKey] = useState("");
  const [connection, setConnection] = useState<ConnectionState>({ kind: "disconnected" });
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [inference, setInference] = useState<InferenceState>({ kind: "idle" });
  const operationsAbortRef = useRef<AbortController | null>(null);
  const inferenceAbortRef = useRef<AbortController | null>(null);

  async function connect(event?: FormEvent) {
    event?.preventDefault();
    operationsAbortRef.current?.abort();
    const controller = new AbortController();
    operationsAbortRef.current = controller;
    setConnection({ kind: "loading" });
    setInference({ kind: "idle" });

    try {
      const snapshot = await operationsClient.load(apiKey, controller.signal);
      setConnection({ kind: "connected", snapshot });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      const message =
        error instanceof OperationsApiError
          ? error.message
          : "Gateway Console could not establish a trusted Operations view.";
      setConnection({ kind: "error", message });
    }
  }

  async function runInference(event: FormEvent) {
    event.preventDefault();
    if (connection.kind !== "connected") {
      setInference({ kind: "error", message: "Connect to the Gateway before running inference." });
      return;
    }

    inferenceAbortRef.current?.abort();
    const controller = new AbortController();
    inferenceAbortRef.current = controller;
    setInference({ kind: "running" });

    try {
      const result = await inferenceClient.generate(apiKey, prompt, controller.signal);
      setInference({ kind: "succeeded", result });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      const message =
        error instanceof InferenceApiError
          ? error.message
          : "Gateway inference could not establish trusted terminal evidence.";
      setInference({ kind: "error", message });
    }
  }

  function disconnect() {
    operationsAbortRef.current?.abort();
    inferenceAbortRef.current?.abort();
    operationsAbortRef.current = null;
    inferenceAbortRef.current = null;
    setApiKey("");
    setPrompt(DEFAULT_PROMPT);
    setInference({ kind: "idle" });
    setConnection({ kind: "disconnected" });
  }

  const connected = connection.kind === "connected" ? connection.snapshot : null;
  const grafanaDashboardUrl = buildLocalGrafanaDashboardUrl(window.location.origin);

  return (
    <main className="shell">
      <header className="masthead">
        <div>
          <p className="eyebrow">Governed AI Platform</p>
          <h1>Gateway Console</h1>
          <p className="subtitle">
            Operational visibility and one bounded governed request. Evidence remains descriptive — model
            authority stays server-side.
          </p>
        </div>
        <div className="boundary-badge" title="Permanent authorization invariant">
          <span>Authority invariant</span>
          <strong>Gateway ⊆ Policy Router</strong>
        </div>
      </header>

      <section className="connection-panel" aria-labelledby="connection-title">
        <div>
          <p className="section-kicker">Gateway access</p>
          <h2 id="connection-title">Connect to the local Gateway</h2>
          <p className="muted">
            The key is held only in this page&apos;s React state and is cleared when you disconnect.
          </p>
        </div>
        <form className="credential-form" onSubmit={connect}>
          <label htmlFor="gateway-api-key">X-Gateway-API-Key</label>
          <div className="credential-row">
            <input
              id="gateway-api-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              disabled={connection.kind === "loading"}
              placeholder="Gateway credential"
            />
            <button className="primary" type="submit" disabled={connection.kind === "loading"}>
              {connection.kind === "loading" ? "Connecting…" : connected ? "Refresh" : "Connect"}
            </button>
            {(connected || connection.kind === "error") && (
              <button className="secondary" type="button" onClick={disconnect}>
                Disconnect
              </button>
            )}
          </div>
        </form>
      </section>

      {connection.kind === "disconnected" && (
        <section className="empty-state" aria-live="polite">
          <span className="status-dot neutral" />
          <div>
            <strong>Disconnected</strong>
            <p>Connect with an explicitly granted Gateway identity to load live operational metadata.</p>
          </div>
        </section>
      )}

      {connection.kind === "loading" && (
        <section className="empty-state" aria-live="polite">
          <span className="status-dot pending" />
          <div>
            <strong>Loading trusted Operations data</strong>
            <p>No cached or fabricated values are shown while requests are in flight.</p>
          </div>
        </section>
      )}

      {connection.kind === "error" && (
        <section className="error-state" role="alert">
          <strong>Operations view unavailable</strong>
          <p>{connection.message}</p>
        </section>
      )}

      {connected && (
        <ConsoleView
          snapshot={connected}
          grafanaDashboardUrl={grafanaDashboardUrl}
          prompt={prompt}
          inference={inference}
          onPromptChange={setPrompt}
          onRunInference={runInference}
        />
      )}
    </main>
  );
}

function ConsoleView({
  snapshot,
  grafanaDashboardUrl,
  prompt,
  inference,
  onPromptChange,
  onRunInference,
}: {
  snapshot: OperationsConsoleSnapshot;
  grafanaDashboardUrl: string | null;
  prompt: string;
  inference: InferenceState;
  onPromptChange: (value: string) => void;
  onRunInference: (event: FormEvent) => void;
}) {
  const { overview, deployments } = snapshot;
  return (
    <div className="console-grid">
      <InferencePanel
        prompt={prompt}
        inference={inference}
        onPromptChange={onPromptChange}
        onRunInference={onRunInference}
      />

      <section className="summary-grid" aria-label="Gateway operational overview">
        <SummaryCard
          label="Registry"
          value={overview.registry.catalog_version}
          detail={`${overview.registry.deployment_count} deployments`}
        />
        <SummaryCard
          label="Ranking policy"
          value={overview.ranking.policy_version}
          detail={`snapshot ${overview.ranking.score_snapshot_id}`}
        />
        <SummaryCard
          label="Process health"
          value={`${overview.health.healthy} healthy`}
          detail={`${overview.health.degraded} degraded · ${overview.health.unhealthy} unhealthy`}
        />
        <SummaryCard
          label="Operational evidence"
          value={overview.operational_evidence.state === "available" ? "Available" : "Not supplied"}
          detail="Availability only — no freshness claim"
        />
      </section>

      {grafanaDashboardUrl && (
        <section className="provenance-panel" aria-labelledby="trace-dashboard-title">
          <div>
            <p className="section-kicker">Trace evidence</p>
            <h2 id="trace-dashboard-title">Local Grafana dashboard</h2>
          </div>
          <p className="muted table-note">
            Opens the reviewed local Tempo-backed dashboard. The Console does not query Grafana directly or
            send the Gateway credential in this navigation. No per-request trace ID is claimed here.
          </p>
          <a
            className="secondary"
            href={grafanaDashboardUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open local trace dashboard
          </a>
        </section>
      )}

      <section className="provenance-panel">
        <div>
          <p className="section-kicker">Provenance</p>
          <h2>Active governed configuration</h2>
        </div>
        <dl className="provenance-list">
          <ProvenanceItem term="Registry source date" value={overview.registry.source_date} />
          <ProvenanceItem term="Registry digest" value={shortDigest(overview.registry.digest)} mono />
          <ProvenanceItem term="Ranking source date" value={overview.ranking.source_date} />
          <ProvenanceItem term="Ranking digest" value={shortDigest(overview.ranking.digest)} mono />
          <ProvenanceItem
            term="Benchmark snapshot"
            value={overview.ranking.benchmark_snapshot_id ?? "Not supplied"}
            mono={overview.ranking.benchmark_snapshot_id !== null}
          />
          <ProvenanceItem
            term="Manual override"
            value={overview.ranking.manual_override_id ?? "None"}
            mono={overview.ranking.manual_override_id !== null}
          />
        </dl>
      </section>

      <section className="deployments-panel">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Deployment catalog</p>
            <h2>Authorized operational visibility</h2>
          </div>
          <span className="scope-pill">health scope: {deployments.health_scope}</span>
        </div>
        <p className="muted table-note">
          Health is process-local. This view does not claim fleet completeness, provider reachability, cost,
          latency, or authorization status.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Deployment</th>
                <th>Provider / model</th>
                <th>Group</th>
                <th>Capabilities</th>
                <th>Context</th>
                <th>Environment</th>
                <th>Health</th>
              </tr>
            </thead>
            <tbody>
              {deployments.deployments.map((deployment) => (
                <DeploymentRow key={deployment.deployment_id} deployment={deployment} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function InferencePanel({
  prompt,
  inference,
  onPromptChange,
  onRunInference,
}: {
  prompt: string;
  inference: InferenceState;
  onPromptChange: (value: string) => void;
  onRunInference: (event: FormEvent) => void;
}) {
  return (
    <section className="inference-panel" aria-labelledby="inference-title">
      <div className="section-heading-row">
        <div>
          <p className="section-kicker">Governed inference</p>
          <h2 id="inference-title">Run one provider-neutral request</h2>
        </div>
        <span className="scope-pill">rag.answer · low · public</span>
      </div>
      <p className="muted table-note">
        The Console declares the workload and limits only. Policy Router authorization, deployment ranking,
        retry, fallback, and provider execution remain server-side.
      </p>
      <form className="inference-form" onSubmit={onRunInference}>
        <label htmlFor="inference-prompt">Prompt</label>
        <textarea
          id="inference-prompt"
          value={prompt}
          maxLength={2000}
          rows={4}
          spellCheck={false}
          disabled={inference.kind === "running"}
          onChange={(event) => onPromptChange(event.target.value)}
        />
        <div className="inference-actions">
          <button className="primary" type="submit" disabled={inference.kind === "running"}>
            {inference.kind === "running" ? "Running governed request…" : "Run governed request"}
          </button>
          <span className="muted">No provider, model, deployment, or fallback selector is exposed.</span>
        </div>
      </form>

      {inference.kind === "running" && (
        <div className="inference-status" aria-live="polite">
          <span className="status-dot pending" />
          <span>Waiting for validated terminal routing, usage, and execution evidence.</span>
        </div>
      )}
      {inference.kind === "error" && (
        <div className="inference-error" role="alert">
          <strong>Governed inference unavailable</strong>
          <p>{inference.message}</p>
        </div>
      )}
      {inference.kind === "succeeded" && <InferenceEvidence result={inference.result} />}
    </section>
  );
}

function InferenceEvidence({ result }: { result: GovernedInferenceResult }) {
  const { routing, execution, usage } = result;
  const totalTokens = usage.total_tokens ?? usage.input_tokens + usage.output_tokens;
  const traceUrl =
    execution.trace_id !== null
      ? buildLocalGrafanaTraceUrl(window.location.origin, execution.trace_id)
      : null;
  return (
    <div className="inference-evidence" aria-live="polite">
      <div className="answer-block">
        <span>Completion</span>
        <p>{result.content}</p>
      </div>
      <div className="inference-summary-grid">
        <SummaryCard
          label="Authorized group"
          value={routing.authorized_model_group}
          detail={`policy ${routing.policy.policy_version}`}
        />
        <SummaryCard
          label="Selected provider"
          value={execution.provider}
          detail={execution.model}
        />
        <SummaryCard
          label="Deployment"
          value={execution.deployment}
          detail={`attempt ${execution.attempt_number} · fallback ${execution.fallback_index}`}
        />
        <SummaryCard
          label="Execution"
          value={`${execution.latency_ms} ms`}
          detail={`${totalTokens} normalized tokens`}
        />
      </div>
      <dl className="provenance-list inference-provenance">
        <ProvenanceItem term="Request ID" value={result.request_id} mono />
        <ProvenanceItem term="Routing decision" value={routing.routing_decision_id} mono />
        <ProvenanceItem
          term="Policy"
          value={`${routing.policy.policy_id} · ${routing.policy.policy_version}`}
        />
        <ProvenanceItem term="Policy decision" value={routing.policy.decision_id} mono />
        <ProvenanceItem term="Registry digest" value={shortDigest(routing.model_registry_digest)} mono />
        <ProvenanceItem term="Ranking policy" value={routing.ranking_policy_version} />
        <ProvenanceItem
          term="Score snapshot"
          value={routing.score_snapshot_id ?? "Not supplied"}
          mono={routing.score_snapshot_id !== null}
        />
        <ProvenanceItem
          term="Fallback sequence"
          value={routing.fallback_sequence.join(" → ")}
          mono
        />
        <ProvenanceItem term="API family" value={execution.api_family ?? "Not supplied"} />
        <ProvenanceItem
          term="Normalized usage"
          value={`${usage.input_tokens} in · ${usage.output_tokens} out`}
        />
        <ProvenanceItem term="Cost evidence" value={usage.total_cost_usd ?? "Not supplied"} />
        <ProvenanceItem
          term="Trace ID"
          value={execution.trace_id ?? "Not supplied"}
          mono={execution.trace_id !== null}
        />
        <ProvenanceItem
          term="Rejected candidates"
          value={
            routing.rejected_candidates.length === 0
              ? "None"
              : routing.rejected_candidates
                  .map((candidate) => `${candidate.deployment}: ${candidate.reason}`)
                  .join(" · ")
          }
        />
      </dl>
      {traceUrl && (
        <a className="secondary" href={traceUrl} target="_blank" rel="noopener noreferrer">
          View this request&apos;s trace in Grafana
        </a>
      )}
    </div>
  );
}

function SummaryCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="summary-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function ProvenanceItem({ term, value, mono = false }: { term: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd className={mono ? "mono" : undefined}>{value}</dd>
    </div>
  );
}

function DeploymentRow({ deployment }: { deployment: OperationsDeployment }) {
  return (
    <tr>
      <td>
        <strong className="mono">{deployment.deployment_id}</strong>
        <span className={deployment.enabled ? "enabled-label" : "disabled-label"}>
          {deployment.enabled ? "enabled" : "disabled"}
        </span>
      </td>
      <td>
        <strong>{deployment.provider}</strong>
        <span className="mono secondary-line">{deployment.model_id}</span>
      </td>
      <td>
        <strong>{deployment.model_group}</strong>
        <span className="secondary-line">{deployment.api_family}</span>
      </td>
      <td>
        <span className="token-list">{deployment.capabilities.join(" · ") || "None declared"}</span>
        <span className="secondary-line">{deployment.modalities.join(" · ")}</span>
      </td>
      <td>{formatContext(deployment.context_tokens)}</td>
      <td>
        <span>{deployment.allowed_environments.join(" · ")}</span>
        <span className="secondary-line">max: {deployment.max_data_classification}</span>
      </td>
      <td>
        <span className={`health-chip ${deployment.health.status}`}>{deployment.health.status}</span>
        <span className="secondary-line">circuit: {deployment.health.circuit_state}</span>
      </td>
    </tr>
  );
}

function shortDigest(value: string): string {
  return value.length > 20 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value;
}

function formatContext(tokens: number): string {
  return tokens >= 1000 ? `${Math.round(tokens / 1000)}k` : String(tokens);
}
