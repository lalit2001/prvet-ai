import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sentry Review",
  description: "Self-hosted AI code review.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        {/* config.js is written at deploy time — see plan.md F9 AC9.2. */}
        <Script src="/config.js" strategy="beforeInteractive" />
      </head>
      <body>{children}</body>
    </html>
  );
}
