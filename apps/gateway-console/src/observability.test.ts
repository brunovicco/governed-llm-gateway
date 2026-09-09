import { describe, expect, it } from "vitest";

import dashboard from "../../../deploy/observability/gateway-traces-dashboard.json";
import {
  GRAFANA_TRACE_DASHBOARD_UID,
  buildLocalGrafanaDashboardUrl,
  buildLocalGrafanaTraceUrl,
} from "./observability";

const VALID_TRACE_ID = "abcdef1234567890abcdef1234567890";

function origin(protocol: string, hostname: string, port: string): string {
  return `${protocol}//${hostname}:${port}`;
}

describe("local Grafana dashboard navigation", () => {
  it("derives the reviewed Grafana dashboard URL from the exact local Console origin", () => {
    const href = buildLocalGrafanaDashboardUrl(origin("http:", "127.0.0.1", "5173"));

    expect(href).not.toBeNull();
    const target = new URL(href!);
    expect(target.protocol).toBe("http:");
    expect(target.hostname).toBe("127.0.0.1");
    expect(target.port).toBe("3000");
    expect(target.pathname).toBe(
      `/d/${GRAFANA_TRACE_DASHBOARD_UID}/governed-llm-gateway-traces`,
    );
    expect(target.search).toBe("");
    expect(target.hash).toBe("");
    expect(target.username).toBe("");
    expect(target.password).toBe("");
  });

  it("keeps the Console link target aligned with the provisioned dashboard UID", () => {
    expect(dashboard.uid).toBe(GRAFANA_TRACE_DASHBOARD_UID);
  });

  it.each([
    origin("https:", "127.0.0.1", "5173"),
    origin("http:", "localhost", "5173"),
    origin("http:", "127.0.0.1", "5174"),
    origin("http:", "127.0.0.2", "5173"),
    "not-a-url",
  ])("rejects unreviewed Console origin %s", (consoleOrigin) => {
    expect(buildLocalGrafanaDashboardUrl(consoleOrigin)).toBeNull();
  });

  it("rejects origins carrying path, query, fragment, or userinfo", () => {
    const base = origin("http:", "127.0.0.1", "5173");
    expect(buildLocalGrafanaDashboardUrl(`${base}/console`)).toBeNull();
    expect(buildLocalGrafanaDashboardUrl(`${base}/?token=secret`)).toBeNull();
    expect(buildLocalGrafanaDashboardUrl(`${base}/#trace`)).toBeNull();
    expect(buildLocalGrafanaDashboardUrl(origin("http:", "user@127.0.0.1", "5173"))).toBeNull();
  });
});

describe("local Grafana per-trace navigation", () => {
  it("builds a dashboard deep link setting the ${traceId} variable and jumping to that panel", () => {
    const href = buildLocalGrafanaTraceUrl(origin("http:", "127.0.0.1", "5173"), VALID_TRACE_ID);

    expect(href).not.toBeNull();
    const target = new URL(href!);
    expect(target.protocol).toBe("http:");
    expect(target.hostname).toBe("127.0.0.1");
    expect(target.port).toBe("3000");
    expect(target.pathname).toBe(`/d/${GRAFANA_TRACE_DASHBOARD_UID}/governed-llm-gateway-traces`);
    expect(target.searchParams.get("var-traceId")).toBe(VALID_TRACE_ID);
    expect(target.searchParams.get("viewPanel")).toBe("2");
  });

  it("targets the panel the provisioned dashboard actually declares", () => {
    const panels = (dashboard as { panels: Array<{ id: number; type: string }> }).panels;
    const tracePanel = panels.find((panel) => panel.type === "traces");
    expect(tracePanel).toBeDefined();
    const href = buildLocalGrafanaTraceUrl(origin("http:", "127.0.0.1", "5173"), VALID_TRACE_ID);
    expect(new URL(href!).searchParams.get("viewPanel")).toBe(String(tracePanel!.id));
  });

  it("rejects a malformed trace ID", () => {
    const base = origin("http:", "127.0.0.1", "5173");
    expect(buildLocalGrafanaTraceUrl(base, "")).toBeNull();
    expect(buildLocalGrafanaTraceUrl(base, "not-hex")).toBeNull();
    expect(buildLocalGrafanaTraceUrl(base, VALID_TRACE_ID.toUpperCase())).toBeNull();
    expect(buildLocalGrafanaTraceUrl(base, VALID_TRACE_ID.slice(0, 31))).toBeNull();
    expect(buildLocalGrafanaTraceUrl(base, `${VALID_TRACE_ID}0`)).toBeNull();
  });

  it.each([
    origin("https:", "127.0.0.1", "5173"),
    origin("http:", "localhost", "5173"),
    origin("http:", "127.0.0.1", "5174"),
    "not-a-url",
  ])("rejects unreviewed Console origin %s", (consoleOrigin) => {
    expect(buildLocalGrafanaTraceUrl(consoleOrigin, VALID_TRACE_ID)).toBeNull();
  });
});
