/** @type {import('next').NextConfig} */
// Standalone server build (used by the Docker image).
const nextConfig = { reactStrictMode: true, output: "standalone" };

export default nextConfig;
