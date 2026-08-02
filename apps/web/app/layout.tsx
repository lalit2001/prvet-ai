import type { Metadata } from "next";
import Script from "next/script";
import { Shell } from "@/components/Shell";
import { ToastProvider } from "@/components/ui";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sentry Review · crv",
  description: "Self-hosted AI code review.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <Script src="/config.js" strategy="beforeInteractive" />
      </head>
      <body>
        <ToastProvider>
          <Shell>{children}</Shell>
        </ToastProvider>
      </body>
    </html>
  );
}
