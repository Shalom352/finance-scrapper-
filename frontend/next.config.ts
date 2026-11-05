import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // Enable strict mode for better development experience
  reactStrictMode: true,

  // API URL for browser requests (inlined at build time). Server components may use
  // INTERNAL_API_URL at runtime instead (see src/lib/api.ts).
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },

  // Self-contained server for the Docker image only (`next start` keeps working locally).
  ...(process.env.NEXT_OUTPUT_STANDALONE === "1" ? { output: "standalone" as const } : {}),

  // No framework fingerprint in the response headers.
  poweredByHeader: false,

  // Security headers on every page (audit 22/10/2026: the UI sent none). next/font self-hosts the fonts,
  // so everything is same-origin; inline scripts are the Next bootstrap. HSTS belongs to the HTTPS proxy.
  async headers() {
    const dev = process.env.NODE_ENV !== "production";
    const csp = [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      `connect-src 'self'${dev ? " ws: http://localhost:8000" : ""}`,
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join("; ");
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
        ],
      },
    ];
  },

  // Browser /api calls go through the proxy (src/proxy.ts adds the internal token) to the backend:
  // the Docker service by default, another instance when API_PROXY_TARGET is set (tests, local runs).
  async rewrites() {
    const target = process.env.API_PROXY_TARGET ?? "http://backend:8000";
    return [{ source: "/api/:path*", destination: `${target}/api/:path*` }];
  },
};

export default withNextIntl(nextConfig);
