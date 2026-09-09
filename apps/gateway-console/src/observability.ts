export const GRAFANA_TRACE_DASHBOARD_UID = "governed-llm-gateway-traces";
export const GRAFANA_TEMPO_DATASOURCE_UID = "tempo";

const LOCAL_CONSOLE_PROTOCOL = "http:";
const LOCAL_CONSOLE_HOSTNAME = "127.0.0.1";
const LOCAL_CONSOLE_PORT = "5173";
const LOCAL_GRAFANA_PORT = "3000";
const GRAFANA_TRACE_DASHBOARD_SLUG = "governed-llm-gateway-traces";
const GRAFANA_TRACE_PANEL_ID = "2";
const TRACE_ID_PATTERN = /^[0-9a-f]{32}$/;

function validatedLocalConsoleTarget(consoleOrigin: string): URL | null {
  let target: URL;
  try {
    target = new URL(consoleOrigin);
  } catch {
    return null;
  }

  if (
    target.protocol !== LOCAL_CONSOLE_PROTOCOL ||
    target.hostname !== LOCAL_CONSOLE_HOSTNAME ||
    target.port !== LOCAL_CONSOLE_PORT ||
    target.username !== "" ||
    target.password !== "" ||
    target.pathname !== "/" ||
    target.search !== "" ||
    target.hash !== ""
  ) {
    return null;
  }

  target.port = LOCAL_GRAFANA_PORT;
  return target;
}

export function buildLocalGrafanaDashboardUrl(consoleOrigin: string): string | null {
  const target = validatedLocalConsoleTarget(consoleOrigin);
  if (target === null) {
    return null;
  }

  target.pathname = `/d/${GRAFANA_TRACE_DASHBOARD_UID}/${GRAFANA_TRACE_DASHBOARD_SLUG}`;
  return target.toString();
}

/**
 * Deep-link to one already-emitted trace, rendered by the provisioned dashboard's own
 * "Selected request trace" panel via its ${traceId} template variable.
 *
 * This reuses the same reviewed, file-provisioned dashboard the Console already links to
 * (`buildLocalGrafanaDashboardUrl`) rather than Grafana's ad hoc Explore view: Explore requires a
 * permission this local demo's anonymous Viewer role does not grant, while a provisioned
 * dashboard panel is already proven reachable by that role. Descriptive navigation only - the
 * trace ID comes from the terminal execution evidence of a request this Console itself just ran,
 * never guessed.
 */
export function buildLocalGrafanaTraceUrl(consoleOrigin: string, traceId: string): string | null {
  if (!TRACE_ID_PATTERN.test(traceId)) {
    return null;
  }
  const target = validatedLocalConsoleTarget(consoleOrigin);
  if (target === null) {
    return null;
  }

  target.pathname = `/d/${GRAFANA_TRACE_DASHBOARD_UID}/${GRAFANA_TRACE_DASHBOARD_SLUG}`;
  target.searchParams.set("var-traceId", traceId);
  target.searchParams.set("viewPanel", GRAFANA_TRACE_PANEL_ID);
  return target.toString();
}
