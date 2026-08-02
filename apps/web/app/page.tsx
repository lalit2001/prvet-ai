"use client";

import { useEffect, useState } from "react";
import { apiBaseUrl } from "@/lib/config";

type HealthState = "loading" | "ok" | "down";

export default function Home() {
  const [health, setHealth] = useState<HealthState>("loading");
  const [base, setBase] = useState("");

  useEffect(() => {
    const u = apiBaseUrl();
    setBase(u);
    fetch(`${u}/healthz`)
      .then((r) => setHealth(r.ok ? "ok" : "down"))
      .catch(() => setHealth("down"));
  }, []);

  const color =
    health === "ok" ? "text-emerald-400" : health === "down" ? "text-red-400" : "text-neutral-400";
  const label = health === "loading" ? "checking…" : health;

  return (
    <main className="mx-auto max-w-4xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Sentry Review</h1>
      <p className="mt-2 text-sm text-neutral-400">
        API: <code className="text-emerald-400">{base || "…"}</code> · status{" "}
        <span className={color}>{label}</span>
      </p>
      <p className="mt-8 text-neutral-300">
        UI stub. Real dashboard lands in M2 — see <code>plan.md</code>.
      </p>
    </main>
  );
}
