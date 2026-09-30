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
};

export default withNextIntl(nextConfig);
