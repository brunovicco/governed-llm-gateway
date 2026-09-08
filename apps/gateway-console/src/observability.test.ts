import { describe, expect, it } from "vitest";

import dashboard from "../../../deploy/observability/gateway-traces-dashboard.json";
import { GRAFANA_TRACE_DASHBOARD_UID, buildLocalGrafanaDashboardUrl } from "./observability";

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
