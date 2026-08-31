/** @type {import('next').NextConfig} */
const path = require('path');

// The Content-Security-Policy header is emitted per request by proxy.js so
// Next.js can attach a fresh nonce to its framework and page scripts.
const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=()' },
  { key: 'X-Frame-Options', value: 'DENY' },
];

const nextConfig = {
  outputFileTracingRoot: path.join(__dirname),
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

module.exports = nextConfig;
