import type { NextConfig } from "next";

// Static export: the whole site is plain HTML/JS hosted for free on GitHub Pages. Live data comes
// from the ComplaintLens API (NEXT_PUBLIC_API_URL) in the browser. NEXT_PUBLIC_BASE_PATH is
// "/ComplainLens" on GitHub Pages and empty locally.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  basePath: basePath || undefined,
  trailingSlash: true, // /en/help/ -> /en/help/index.html, which GitHub Pages serves directly
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
