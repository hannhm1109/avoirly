import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  distDir: process.env.AVOIRLY_E2E === "1" ? ".next-e2e" : ".next",
  poweredByHeader: false,
  devIndicators: false,
  experimental: { proxyClientMaxBodySize: "11mb" },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Strict-Transport-Security", value: "max-age=31536000" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};
export default config;
