/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export — required for S3/SWA/Blob hosting. See plan.md §11 + F9.
  output: "export",
  images: { unoptimized: true },
  reactStrictMode: true,
  trailingSlash: true,
};
export default nextConfig;
