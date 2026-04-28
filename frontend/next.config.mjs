/** @type {import('next').NextConfig} */
const nextConfig = {
  assetPrefix: process.env.NODE_ENV === "production" ? "." : undefined,
  output: "export",
  reactStrictMode: true,
  trailingSlash: true
};

export default nextConfig;
