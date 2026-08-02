"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type Finding, type ReviewResult } from "@/lib/api";

const sevColor: Record<string, string> = {
  critical: "text-red-400 bg-red-950/40 border-red-900",
  high: "text-orange-400 bg-orange-950/40 border-orange-900",
  medium: "text-yellow-400 bg-yellow-950/40 border-yellow-900",
  low: "text-blue-400 bg-blue-950/40 border-blue-900",
  info: "text-neutral-400 bg-neutral-900 border-neutral-800",
};

const SAMPLE = `def divide(a, b):
    return a / b

def get_user(user_id):
    return db.execute("SELECT * FROM users WHERE id = " + user_id)
`;

function RepoInner() {
  const sp = useSearchParams();
  const id = sp.get("id") || "";

  const [findings, setFindings] = useState<Finding[]>([]);
  const [baseline, setBaseline] = useState<{ files_indexed: number; symbols: number } | null>(null);
  const [busy, setBusy] = useState<"idle" | "baseline" | "review">("idle");
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState(SAMPLE);
  const [language, setLanguage] = useState("python");
  const [result, setResult] = useState<ReviewResult | null>(null);

  async function refresh() {
    if (!id) return;
    try { setFindings(await api.repos.findings(id)); }
    catch (e) { setError(String(e)); }
  }
  useEffect(() => { refresh(); }, [id]);

  if (!id) {
    return <p className="p-8 text-sm text-neutral-500">No repo selected. <Link href="/" className="text-emerald-400">Back →</Link></p>;
  }

  async function runBaseline() {
    setBusy("baseline"); setError(null);
    try {
      const b = await api.repos.baseline(id);
      setBaseline({ files_indexed: b.files_indexed, symbols: b.symbols });
    } catch (e) { setError(String(e)); }
    finally { setBusy("idle"); }
  }

  async function runReview() {
    setBusy("review"); setError(null); setResult(null);
    try {
      const r = await api.reviews.adhoc(code, language, id);
      setResult(r);
      await refresh();
    } catch (e) { setError(String(e)); }
    finally { setBusy("idle"); }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <Link href="/" className="text-xs text-neutral-500 hover:text-neutral-300">← All repos</Link>
      <div className="mt-2 flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          Repo <code className="text-emerald-400">{id.slice(0, 8)}</code>
        </h1>
        <Link href={`/repo/settings?id=${id}`} className="text-xs text-neutral-400 hover:text-neutral-200">Settings →</Link>
      </div>

      {error && (
        <pre className="mt-4 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-300 whitespace-pre-wrap">{error}</pre>
      )}

      <section className="mt-8 grid gap-6 md:grid-cols-2">
        <div className="rounded border border-neutral-800 p-4">
          <h2 className="text-sm uppercase tracking-wider text-neutral-500">Baseline (M2)</h2>
          <p className="mt-2 text-sm text-neutral-400">Walk the repo, extract Python symbols, snapshot the graph.</p>
          <button
            onClick={runBaseline} disabled={busy !== "idle"}
            className="mt-3 rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy === "baseline" ? "Running…" : "Run baseline"}
          </button>
          {baseline && (
            <p className="mt-3 text-sm text-emerald-400">
              Indexed {baseline.files_indexed} files · {baseline.symbols} symbols.
            </p>
          )}
        </div>

        <div className="rounded border border-neutral-800 p-4">
          <h2 className="text-sm uppercase tracking-wider text-neutral-500">Ad-hoc LLM review</h2>
          <p className="mt-2 text-sm text-neutral-400">Paste code; LLM returns structured findings. Persists to this repo.</p>
          <div className="mt-3 flex items-center gap-2">
            <label className="text-xs text-neutral-500">Language</label>
            <select
              value={language} onChange={(e) => setLanguage(e.target.value)}
              className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-xs"
            >
              {["python", "typescript", "javascript", "go", "java", "rust", "sql"].map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
          <textarea
            value={code} onChange={(e) => setCode(e.target.value)}
            className="mt-3 h-64 w-full rounded border border-neutral-800 bg-neutral-950 p-3 font-mono text-xs"
            spellCheck={false}
          />
          <button
            onClick={runReview} disabled={busy !== "idle"}
            className="mt-3 rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy === "review" ? "Reviewing…" : "Review"}
          </button>
          {result?.error && (
            <p className="mt-3 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-300">{result.error}</p>
          )}
          {result?.summary && (
            <p className="mt-3 rounded border border-neutral-800 bg-neutral-950 p-3 text-xs text-neutral-300 whitespace-pre-wrap">{result.summary}</p>
          )}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">Findings ({findings.length})</h2>
        {findings.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-500">No findings yet. Run a review above.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {findings.map((f) => (
              <div key={f.id} className={`rounded border p-4 ${sevColor[f.severity] || sevColor.info}`}>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="uppercase tracking-wider">{f.severity} · {f.category}</span>
                  <span className="text-neutral-500">conf {f.confidence.toFixed(2)} · {f.source}</span>
                </div>
                <h3 className="mt-1 text-sm font-medium text-neutral-100">{f.title}</h3>
                {f.file_path && f.file_path !== "adhoc" && (
                  <p className="mt-1 text-xs font-mono text-neutral-500">
                    {f.file_path}{f.start_line ? `:${f.start_line}` : ""}
                  </p>
                )}
                <p className="mt-2 text-sm text-neutral-300 whitespace-pre-wrap">{f.body}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

// useSearchParams requires a Suspense boundary when used in a client component under static export.
export default function RepoPage() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-neutral-500">Loading…</p>}>
      <RepoInner />
    </Suspense>
  );
}
