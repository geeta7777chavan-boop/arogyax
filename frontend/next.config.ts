/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
 
  // Proxy /api/* → backend (works both locally and on Vercel)
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_BASE_URL}/:path*`,
      },
    ];
  },
 
  // Allow images from Supabase storage
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.supabase.co",
      },
    ],
  },
};
 
module.exports = nextConfig;