/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The standalone server (node .next/standalone/server.js) is what the local
  // Docker-style supervisor serves. Vercel builds and serves Next.js itself, so
  // it must not use standalone there (VERCEL is set in Vercel's build env).
  output: process.env.VERCEL ? undefined : "standalone",
  env: {
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
