"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Repo } from "@/lib/api";

export default function Home() {
  const [status, setStatus] = useState<"loading" | "ok" | "down">("loading");
  const [repos, setRepos] = useState<Repo[]>([]);
  const [name, setName] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      await api.health();
      setStatus("ok");
      setRepos(await api.repos.list());
    } catch (e) {
      setStatus("down");
      setError(String(e));
    }
  }

  useEffect(() => { refresh(); }, []);

  async function addRepo(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api.repos.createLocal(name, localPath);
      setName(""); setLocalPath("");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <header className="flex items-baseline justify-between">
        <h1 className="text-3xl font-semibold tracking-tight">Sentry Review</h1>
        <span className={`text-xs ${status === "ok" ? "text-emerald-400" : status === "down" ? "text-red-400" : "text-neutral-400"}`}>
          API {status}
        </span>
      </header>

      {error && (
        <pre className="mt-4 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-300 whitespace-pre-wrap">{error}</pre>
      )}

      <section className="mt-8">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">Add a local repo</h2>
        <form onSubmit={addRepo} className="mt-3 flex flex-wrap gap-2">
          <input
            className="flex-1 min-w-[180px] rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm"
            placeholder="Name (e.g. my-project)"
            value={name} onChange={(e) => setName(e.target.value)} required
          />
          <input
            className="flex-[2] min-w-[280px] rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm font-mono"
            placeholder="/absolute/path/to/repo"
            value={localPath} onChange={(e) => setLocalPath(e.target.value)} required
          />
          <button
            type="submit" disabled={busy}
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy ? "…" : "Add"}
          </button>
        </form>
      </section>

      <section className="mt-10">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">Repositories</h2>
        {repos.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-500">No repos yet. Add one above.</p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-neutral-500">
                <th className="py-2">Name</th>
                <th>Path</th>
                <th>Enabled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {repos.map((r) => (
                <tr key={r.id} className="border-t border-neutral-900">
                  <td className="py-3">{r.full_name}</td>
                  <td className="font-mono text-xs text-neutral-400">{r.clone_url}</td>
                  <td>{r.is_enabled ? "yes" : "no"}</td>
                  <td className="text-right">
                    <Link href={`/repo?id=${r.id}`} className="text-emerald-400 hover:underline">Open →</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <footer className="mt-16 text-xs text-neutral-600">
        M0-M2 live · Ad-hoc LLM review on repo detail · Config lives in <code>.env</code>
      </footer>
    </main>
  );
}
