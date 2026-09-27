import type { NextConfig } from "next";

const api = process.env.AVOIRLY_API_ORIGIN || "http://127.0.0.1:8000";
const origin = new URL(api);
if (
  !["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname) ||
  origin.protocol !== "http:" ||
  origin.pathname !== "/"
) {
  throw new Error("Phase 3 requires a local HTTP API origin.");
}

const config: NextConfig = {
  distDir: process.env.AVOIRLY_E2E === "1" ? ".next-e2e" : ".next",
  poweredByHeader: false,
  devIndicators: false,
  experimental: { proxyClientMaxBodySize: "11mb" },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${origin.origin}/api/v1/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};
export default config;
