import { describe, expect, it } from "vitest";

import config from "../vite.config";

const expectedSecurityHeaders = {
  "Content-Security-Policy": "frame-ancestors 'none'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
};

describe("local Console server boundary", () => {
  it("emits the reviewed anti-framing and browser hardening headers", () => {
    expect(config.server?.headers).toEqual(expectedSecurityHeaders);
  });

  it("preserves the exact loopback server and Gateway proxy boundary", () => {
    expect(config.server?.host).toBe("127.0.0.1");
    expect(config.server?.port).toBe(5173);
    expect(config.server?.strictPort).toBe(true);
    expect(config.server?.proxy?.["/v1"]).toEqual({
      target: "http://127.0.0.1:8000",
      changeOrigin: false,
    });
  });
});
