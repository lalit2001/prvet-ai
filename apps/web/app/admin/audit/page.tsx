"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function AuditPage() {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [runs, setRuns] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.admin.audit(), api.admin.runs()])
      .then(([a, r]) => { setRows(a); setRuns(r); })
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Audit &amp; runs</h1>

      {error && <pre className="mt-4 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-300">{error}</pre>}

      <section className="mt-8">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">Recent runs</h2>
        {runs.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-500">No runs yet.</p>
        ) : (
          <table className="mt-3 w-full text-xs">
            <thead className="text-left text-neutral-500">
              <tr><th className="py-1">Repo</th><th>Type</th><th>Status</th><th>Commit</th><th>Duration</th><th>When</th></tr>
            </thead>
            <tbody>
              {runs.map((r, i) => (
                <tr key={i} className="border-t border-neutral-900">
                  <td className="py-2">{String(r.repo ?? "")}</td>
                  <td>{String(r.run_type)}</td>
                  <td className={r.status === "succeeded" ? "text-emerald-400" : r.status === "failed" ? "text-red-400" : "text-neutral-400"}>{String(r.status)}</td>
                  <td className="font-mono">{String(r.commit_sha ?? "").slice(0, 10)}</td>
                  <td>{r.duration_ms ? `${r.duration_ms}ms` : "-"}</td>
                  <td className="text-neutral-500">{String(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">Audit log</h2>
        {rows.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-500">Nothing logged yet.</p>
        ) : (
          <table className="mt-3 w-full text-xs">
            <thead className="text-left text-neutral-500">
              <tr><th className="py-1">When</th><th>Actor</th><th>Action</th><th>Resource</th></tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-neutral-900">
                  <td className="py-2 text-neutral-500">{String(r.created_at)}</td>
                  <td>{String(r.actor_type)} {r.actor_id ? String(r.actor_id).slice(0, 12) : ""}</td>
                  <td className="font-mono">{String(r.action)}</td>
                  <td>{String(r.resource_type)} {r.resource_id ? String(r.resource_id).slice(0, 12) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
