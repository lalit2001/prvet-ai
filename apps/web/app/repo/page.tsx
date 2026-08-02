"use client";

import clsx from "clsx";
import { AlertOctagon, ArrowLeft, Play, Settings, Zap } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type Finding, type Repo, type RepoConfig, type ReviewResult } from "@/lib/api";
import {
  Button, Card, CardBody, CardHeader, EmptyState, PageHeader,
  SeverityBadge, StatCard, StatusPill, useToast,
} from "@/components/ui";

const SAMPLE = `def divide(a, b):
    return a / b

def get_user(user_id):
    return db.execute("SELECT * FROM users WHERE id = " + user_id)
`;

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "findings", label: "Findings" },
  { id: "review",   label: "Ad-hoc review" },
  { id: "settings", label: "Settings" },
] as const;
type TabId = typeof TABS[number]["id"];

type BaselineResult = {
  files_seen: number;
  files_indexed: number;
  files_skipped: number;
  symbols: number;
  cached?: boolean;
  by_language: Record<string, number>;
};

function RepoInner() {
  const sp = useSearchParams();
  const id = sp.get("id") || "";
  const toast = useToast();

  const [tab, setTab] = useState<TabId>("overview");
  const [repo, setRepo] = useState<Repo | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [baseline, setBaseline] = useState<BaselineResult | null>(null);
  const [busy, setBusy] = useState<"idle" | "baseline" | "review">("idle");
  const [code, setCode] = useState(SAMPLE);
  const [language, setLanguage] = useState("python");
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [cfg, setCfg] = useState<RepoConfig | null>(null);

  async function refresh() {
    if (!id) return;
    try {
      const all = await api.repos.list();
      setRepo(all.find(r => r.id === id) ?? null);
    } catch { /* ignore */ }
    try { setFindings(await api.repos.findings(id)); } catch { /* ignore */ }
    try { setCfg(await api.repos.getConfig(id)); } catch { /* ignore */ }
  }
  useEffect(() => { refresh(); }, [id]);

  if (!id) return <EmptyState icon={AlertOctagon} title="No repo selected" hint="Pick one from the Repositories page." />;

  async function runBaseline() {
    setBusy("baseline");
    try {
      const b = await api.repos.baseline(id);
      setBaseline(b);
      const langBreakdown = Object.entries(b.by_language || {}).map(([k, v]) => `${v} ${k}`).join(", ");
      if (b.cached) {
        toast({ kind: "info", msg: `Cached — same commit already baselined (${b.files_indexed} files)` });
      } else if (b.files_indexed === 0) {
        toast({ kind: "info",
                msg: `Walked ${b.files_seen} files; indexed 0. No supported languages found (Python + JS/TS/TSX).` });
      } else {
        toast({ kind: "success",
                msg: `${b.files_indexed} of ${b.files_seen} files · ${b.symbols} symbols · ${langBreakdown}` });
      }
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
    finally { setBusy("idle"); }
  }

  async function runReview() {
    setBusy("review"); setResult(null);
    try {
      const r = await api.reviews.adhoc(code, language, id);
      setResult(r);
      if (r.error) toast({ kind: "error", msg: r.error });
      else toast({ kind: "success", msg: `${r.findings.length} finding(s)` });
      await refresh();
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
    finally { setBusy("idle"); }
  }

  return (
    <>
      <div className="mb-6">
        <Link href="/repos" className="inline-flex items-center gap-1 text-xs text-text-3 hover:text-text-1">
          <ArrowLeft className="h-3 w-3" /> All repositories
        </Link>
      </div>
      <PageHeader
        title={repo?.full_name ?? `Repository ${id.slice(0, 8)}`}
        actions={<Link href={`/repo/settings?id=${id}`}
          className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-panel-2 inline-flex items-center gap-1.5">
          <Settings className="h-3.5 w-3.5" /> Settings
        </Link>}
      />
      {repo && (
        <div className="mb-6 flex flex-wrap items-center gap-2 text-xs text-text-3">
          <span className="mono">{repo.clone_url}</span>
          <span>·</span>
          <span className="mono">{repo.default_branch}</span>
          <span>·</span>
          <span className={repo.is_enabled ? "text-emerald-400" : "text-text-3"}>
            {repo.is_enabled ? "enabled" : "disabled"}
          </span>
        </div>
      )}

      <div className="mb-6 flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={clsx(
              "border-b-2 px-4 py-2 text-sm transition-colors",
              tab === t.id ? "border-emerald-500 text-text-1" : "border-transparent text-text-3 hover:text-text-1",
            )}
          >{t.label}</button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard icon={AlertOctagon} label="Open findings"
              value={findings.filter(f => f.status === "open").length}
              tone={findings.length > 0 ? "warn" : "success"} />
            <StatCard icon={Zap} label="Last baseline"
              value={baseline ? `${baseline.files_indexed}/${baseline.files_seen}` : "–"}
              hint={baseline ? `${baseline.symbols} symbols · ${langsText(baseline.by_language)}` : "run one"} />
            <StatCard icon={Play} label="Runs" value="—" hint="see Runs tab" />
          </div>

          <Card>
            <CardHeader title="Baseline analysis"
              subtitle="Walk the repo, extract symbols (Python via ast, JS/TS/TSX via tree-sitter), snapshot the graph"
              action={<Button onClick={runBaseline} disabled={busy !== "idle"}>{busy === "baseline" ? "Running…" : "Run baseline"}</Button>} />
            <CardBody>
              {baseline ? (
                <>
                  <div className="text-sm text-text-2">
                    Walked <b className="text-text-1">{baseline.files_seen}</b> files ·
                    Indexed <b className="text-text-1">{baseline.files_indexed}</b> ·
                    Extracted <b className="text-text-1">{baseline.symbols}</b> symbols
                    {baseline.cached && <span className="ml-2 text-xs text-text-3">(cached — same commit)</span>}
                  </div>
                  {Object.keys(baseline.by_language || {}).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      {Object.entries(baseline.by_language).map(([k, v]) => (
                        <span key={k} className="rounded-md border border-border bg-panel-2 px-2 py-0.5 text-text-2">
                          <span className="mono">{k}</span>&nbsp;<span className="tabular-nums text-text-1">{v}</span>
                        </span>
                      ))}
                    </div>
                  )}
                  {baseline.files_indexed === 0 && (
                    <p className="mt-3 rounded-md border border-yellow-900/60 bg-yellow-950/20 p-3 text-xs text-yellow-200">
                      Walked {baseline.files_seen} files but indexed 0 — this repo has no <code>.py / .js / .jsx / .ts / .tsx</code> files. Other Tier-1 languages (Java, Go) land next.
                    </p>
                  )}
                </>
              ) : (
                <div className="text-sm text-text-3">No baseline yet.</div>
              )}
            </CardBody>
          </Card>
        </div>
      )}

      {tab === "findings" && (
        <Card>
          <CardHeader title="Findings" subtitle={`${findings.length} total, latest first`} />
          <CardBody className="p-0">
            {findings.length === 0 ? (
              <div className="p-8"><EmptyState icon={AlertOctagon} title="No findings" hint="Run an ad-hoc review or open a PR on this repo." /></div>
            ) : (
              <ul className="divide-y divide-border">
                {findings.map((f) => <FindingRow key={f.id} f={f} />)}
              </ul>
            )}
          </CardBody>
        </Card>
      )}

      {tab === "review" && (
        <Card>
          <CardHeader title="Ad-hoc LLM review" subtitle="Paste code, get structured findings. Persists to this repo." />
          <CardBody className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-3">Language</span>
              <select value={language} onChange={(e) => setLanguage(e.target.value)} className="px-2 py-1 text-xs">
                {["python","typescript","javascript","go","java","rust","sql","yaml","dockerfile"].map(l => <option key={l}>{l}</option>)}
              </select>
            </div>
            <textarea value={code} onChange={(e) => setCode(e.target.value)}
              className="h-72 w-full p-3 mono text-xs" spellCheck={false} />
            <div className="flex items-center gap-3">
              <Button onClick={runReview} disabled={busy !== "idle"}>{busy === "review" ? "Reviewing…" : "Review"}</Button>
              {result?.stats?.latency_ms ? <span className="text-xs text-text-3">{String(result.stats.model)} · {String(result.stats.latency_ms)}ms</span> : null}
            </div>
            {result?.error && <p className="rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-300">{result.error}</p>}
            {result?.summary && <p className="rounded-md border border-border bg-panel-2 p-3 text-xs text-text-2 whitespace-pre-wrap">{result.summary}</p>}
          </CardBody>
        </Card>
      )}

      {tab === "settings" && (
        <Card>
          <CardHeader title="Per-repo settings"
            subtitle="Stored in repositories.config."
            action={<Link href={`/repo/settings?id=${id}`} className="text-xs text-emerald-400 hover:underline inline-flex items-center gap-1"><Settings className="h-3 w-3" /> Full editor →</Link>} />
          <CardBody>
            {cfg ? (
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Def k="Block severity ≥" v={cfg.review.block_severity} />
                <Def k="Min confidence" v={cfg.review.min_confidence.toFixed(2)} />
                <Def k="Categories" v={cfg.review.categories.join(", ") || "–"} />
                <Def k="Review drafts" v={cfg.review.drafts ? "yes" : "no"} />
                <Def k="Exclude paths" v={cfg.exclude_paths.length ? cfg.exclude_paths.join(", ") : "–"} />
                <Def k="Weekly schedule" v={<code className="mono">{cfg.weekly.schedule}</code>} />
              </dl>
            ) : <p className="text-sm text-text-3">Loading…</p>}
          </CardBody>
        </Card>
      )}
    </>
  );
}

function langsText(by: Record<string, number>): string {
  const entries = Object.entries(by || {});
  if (!entries.length) return "no languages";
  return entries.map(([k, v]) => `${v} ${k}`).join(" · ");
}

function Def({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-panel-2 p-3">
      <div className="text-xs text-text-3">{k}</div>
      <div className="mt-1 text-sm text-text-1">{v}</div>
    </div>
  );
}

function FindingRow({ f }: { f: Finding }) {
  const [open, setOpen] = useState(false);
  return (
    <li>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start justify-between gap-3 px-5 py-3 text-left hover:bg-panel-2/60">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <SeverityBadge severity={f.severity} />
            <span className="text-[10px] uppercase tracking-wider text-text-3">{f.category}</span>
            <StatusPill status={f.status} />
          </div>
          <div className="mt-1 text-sm text-text-1">{f.title}</div>
          {f.file_path && f.file_path !== "adhoc" && (
            <div className="mono mt-1 text-[11px] text-text-3">{f.file_path}{f.start_line ? `:${f.start_line}` : ""}</div>
          )}
        </div>
        <div className="shrink-0 text-xs text-text-3">conf {f.confidence.toFixed(2)}</div>
      </button>
      {open && f.body && (
        <div className="px-5 pb-4 text-sm text-text-2 whitespace-pre-wrap">{f.body}</div>
      )}
    </li>
  );
}

export default function RepoPage() {
  return <Suspense fallback={<p className="text-sm text-text-3">Loading…</p>}><RepoInner /></Suspense>;
}
