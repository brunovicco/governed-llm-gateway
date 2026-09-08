export const GRAFANA_TRACE_DASHBOARD_UID = "governed-llm-gateway-traces";

const LOCAL_CONSOLE_PROTOCOL = "http:";
const LOCAL_CONSOLE_HOSTNAME = "127.0.0.1";
const LOCAL_CONSOLE_PORT = "5173";
const LOCAL_GRAFANA_PORT = "3000";
const GRAFANA_TRACE_DASHBOARD_SLUG = "governed-llm-gateway-traces";

export function buildLocalGrafanaDashboardUrl(consoleOrigin: string): string | null {
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
  target.pathname = `/d/${GRAFANA_TRACE_DASHBOARD_UID}/${GRAFANA_TRACE_DASHBOARD_SLUG}`;
  return target.toString();
}
