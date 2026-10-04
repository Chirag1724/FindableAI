/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  transpilePackages: ["recharts"],
  async rewrites() {
    const backendUrl =
      process.env.NEXT_PUBLIC_API_URL ||
      process.env.BACKEND_URL ||
      "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl.replace(/\/$/, "")}/api/:path*`,
      },
      {
        source: "/docs",
        destination: `${backendUrl.replace(/\/$/, "")}/docs`,
      },
      {
        source: "/openapi.json",
        destination: `${backendUrl.replace(/\/$/, "")}/openapi.json`,
      },
    ];
  },
};

module.exports = nextConfig;
