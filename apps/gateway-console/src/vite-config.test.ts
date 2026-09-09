import { describe, expect, it } from "vitest";
import type { ProxyOptions } from "vite";

import config from "../vite.config";

const expectedSecurityHeaders = {
  "Content-Security-Policy": "frame-ancestors 'none'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
};

function gatewayProxy(): ProxyOptions {
  const proxy = config.server?.proxy?.["/v1"];
  if (typeof proxy !== "object" || proxy === null) {
    throw new Error("reviewed Gateway proxy must be configured as structured options");
  }
  return proxy;
}

describe("local Console server boundary", () => {
  it("emits the reviewed anti-framing and browser hardening headers", () => {
    expect(config.server?.headers).toEqual(expectedSecurityHeaders);
  });

  it("preserves the exact loopback server and Gateway proxy boundary", () => {
    expect(config.server?.host).toBe("127.0.0.1");
    expect(config.server?.port).toBe(5173);
    expect(config.server?.strictPort).toBe(true);

    const proxy = gatewayProxy();
    expect(proxy.changeOrigin).toBe(false);
    if (typeof proxy.target !== "string") {
      throw new Error("reviewed Gateway proxy target must be a URL string");
    }
    const target = new URL(proxy.target);
    expect(target.protocol).toBe("http:");
    expect(target.hostname).toBe("127.0.0.1");
    expect(target.port).toBe("8000");
    expect(target.pathname).toBe("/");
    expect(target.search).toBe("");
    expect(target.hash).toBe("");
    expect(target.username).toBe("");
    expect(target.password).toBe("");
  });
});
