import { type FormEvent, useRef, useState } from "react";

import { OperationsApiClient, OperationsApiError } from "./api";
import type { OperationsConsoleSnapshot, OperationsDeployment } from "./types";

const operationsClient = new OperationsApiClient();

type ConnectionState =
  | { kind: "disconnected" }
  | { kind: "loading" }
  | { kind: "connected"; snapshot: OperationsConsoleSnapshot }
  | { kind: "error"; message: string };

export function App() {
  const [apiKey, setApiKey] = useState("");
  const [connection, setConnection] = useState<ConnectionState>({ kind: "disconnected" });
  const abortRef = useRef<AbortController | null>(null);

  async function connect(event?: FormEvent) {
    event?.preventDefault();
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setConnection({ kind: "loading" });

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

  function disconnect() {
    abortRef.current?.abort();
    abortRef.current = null;
    setApiKey("");
    setConnection({ kind: "disconnected" });
  }

  const connected = connection.kind === "connected" ? connection.snapshot : null;

  return (
    <main className="shell">
      <header className="masthead">
        <div>
          <p className="eyebrow">Governed AI Platform</p>
          <h1>Gateway Console</h1>
          <p className="subtitle">
            Read-only operational visibility. Evidence, telemetry, and health remain descriptive — never
            authority.
          </p>
        </div>
        <div className="boundary-badge" title="Permanent authorization invariant">
          <span>Authority invariant</span>
          <strong>Gateway ⊆ Policy Router</strong>
        </div>
      </header>

      <section className="connection-panel" aria-labelledby="connection-title">
        <div>
          <p className="section-kicker">Operations access</p>
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
              placeholder="Operations read credential"
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
            <p>Connect with an explicitly granted Operations identity to load live Gateway metadata.</p>
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

      {connected && <ConsoleView snapshot={connected} />}
    </main>
  );
}

function ConsoleView({ snapshot }: { snapshot: OperationsConsoleSnapshot }) {
  const { overview, deployments } = snapshot;
  return (
    <div className="console-grid">
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
