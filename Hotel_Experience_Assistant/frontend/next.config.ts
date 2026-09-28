import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  // Static export needs a real index.html per route directory so a plain
  // static file server (Starlette's StaticFiles(html=True)) can resolve
  // "/admin" -> "admin/index.html" instead of a sibling "admin.html".
  trailingSlash: true,
};

export default nextConfig;
