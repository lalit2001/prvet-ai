import type { Metadata } from "next";
import Script from "next/script";
import { Shell } from "@/components/Shell";
import { ToastProvider } from "@/components/ui";
import "./globals.css";

export const metadata: Metadata = {
  title: "PRVet",
  description: "Self-hosted AI code review that dynamically analyzes pull requests for security, logic defects, and blast radius context.",
  icons: {
    icon: "/logo.svg",
    shortcut: "/logo.svg",
    apple: "/logo.svg",
  },
  openGraph: {
    title: "PRVet",
    description: "Self-hosted AI code review that keeps your source code securely inside your network.",
    images: ["/logo.svg"],
  },
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
