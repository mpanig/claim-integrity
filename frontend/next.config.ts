import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Old routes from before the AEO / GEO rename keep working.
  async redirects() {
    return [
      { source: "/ai-visibility", destination: "/aeo", permanent: true },
      { source: "/ai-visibility/answers", destination: "/aeo/answers", permanent: true },
      { source: "/ai-visibility/coverage", destination: "/aeo/coverage", permanent: true },
      { source: "/ai-visibility/library", destination: "/aeo/prompts", permanent: true },
      { source: "/ai-visibility/plan", destination: "/aeo/prompts/plan", permanent: true },
      { source: "/audit", destination: "/aeo/content", permanent: true },
    ];
  },
  // The browser calls /api/*; Next forwards it to the FastAPI backend.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
