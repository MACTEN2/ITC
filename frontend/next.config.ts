import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The dev server is commonly opened via 127.0.0.1 (IDE previews, this
  // project's own README) rather than localhost. Without this, Next blocks
  // the HMR WebSocket as cross-origin, which throws during the client
  // bundle's dev-only HMR init and can prevent the page from hydrating at
  // all -- not just a noisy console warning.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
