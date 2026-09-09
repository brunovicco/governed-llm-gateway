import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const securityHeaders = {
  "Content-Security-Policy": "frame-ancestors 'none'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
} as const;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    headers: securityHeaders,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
});
