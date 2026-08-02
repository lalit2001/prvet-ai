"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type RepoConfig } from "@/lib/api";

const SEVERITIES = ["critical", "high", "medium", "low", "info"] as const;
const CATEGORIES = ["security", "bug", "performance", "maintainability", "style", "dependency", "test"] as const;
const ROLES = ["admin", "maintain", "write", "read"] as const;

function Inner() {
  const sp = useSearchParams();
  const id = sp.get("id") || "";

  const [cfg, setCfg] = useState<RepoConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!id) return;
    api.repos.getConfig(id).then(setCfg).catch((e) => setError(String(e)));
  }, [id]);

  if (!id) return <p className="p-8 text-sm text-neutral-500">No repo id.</p>;
  if (error) return <pre className="m-8 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-300">{error}</pre>;
  if (!cfg) return <p className="p-8 text-sm text-neutral-500">Loading…</p>;

  async function save() {
    if (!cfg) return;
    setError(null); setSaved(false);
    try {
      const updated = await api.repos.putConfig(id, cfg);
      setCfg(updated); setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) { setError(String(e)); }
  }

  const toggleCategory = (c: string) => {
    const has = cfg.review.categories.includes(c);
    setCfg({ ...cfg, review: { ...cfg.review, categories: has ? cfg.review.categories.filter(x => x !== c) : [...cfg.review.categories, c] } });
  };
  const toggleRole = (r: string) => {
    const has = cfg.bypass.roles.includes(r);
    setCfg({ ...cfg, bypass: { ...cfg.bypass, roles: has ? cfg.bypass.roles.filter(x => x !== r) : [...cfg.bypass.roles, r] } });
  };

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <Link href={`/repo?id=${id}`} className="text-xs text-neutral-500 hover:text-neutral-300">← Back to repo</Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Repo settings</h1>
      <p className="mt-1 text-xs text-neutral-500">Persists to <code>repositories.config</code>. Equivalent of <code>.crv.yml</code>.</p>

      <Section title="Review">
        <Field label="Block merge at severity ≥">
          <select className={inp} value={cfg.review.block_severity}
            onChange={(e) => setCfg({ ...cfg, review: { ...cfg.review, block_severity: e.target.value } })}>
            {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Categories gated on">
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((c) => (
              <label key={c} className="flex items-center gap-1 text-xs">
                <input type="checkbox" checked={cfg.review.categories.includes(c)} onChange={() => toggleCategory(c)} />
                {c}
              </label>
            ))}
          </div>
        </Field>
        <Field label={`Min confidence (${cfg.review.min_confidence.toFixed(2)})`}>
          <input type="range" min={0} max={1} step={0.05} value={cfg.review.min_confidence}
            onChange={(e) => setCfg({ ...cfg, review: { ...cfg.review, min_confidence: parseFloat(e.target.value) } })}
            className="w-full" />
        </Field>
        <Field label="Review draft PRs">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={cfg.review.drafts}
              onChange={(e) => setCfg({ ...cfg, review: { ...cfg.review, drafts: e.target.checked } })} />
            enabled
          </label>
        </Field>
        <Field label="Guidelines (prepended to LLM prompt)">
          <textarea className={`${inp} h-24 font-mono text-xs`} value={cfg.review.guidelines}
            onChange={(e) => setCfg({ ...cfg, review: { ...cfg.review, guidelines: e.target.value } })} />
        </Field>
      </Section>

      <Section title="Bypass">
        <Field label="Roles allowed to bypass">
          <div className="flex flex-wrap gap-2">
            {ROLES.map((r) => (
              <label key={r} className="flex items-center gap-1 text-xs">
                <input type="checkbox" checked={cfg.bypass.roles.includes(r)} onChange={() => toggleRole(r)} />
                {r}
              </label>
            ))}
          </div>
        </Field>
        <Field label="Require second approver for severities (comma-sep)">
          <input className={inp} value={cfg.bypass.require_second_approver_for.join(",")}
            onChange={(e) => setCfg({ ...cfg, bypass: { ...cfg.bypass, require_second_approver_for: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) } })} />
        </Field>
      </Section>

      <Section title="Exclusions & hotspots">
        <Field label="Exclude paths (one per line, glob)">
          <textarea className={`${inp} h-20 font-mono text-xs`} value={cfg.exclude_paths.join("\n")}
            onChange={(e) => setCfg({ ...cfg, exclude_paths: e.target.value.split("\n").filter(Boolean) })} />
        </Field>
        <Field label="Hotspot count for baseline LLM review">
          <input type="number" className={inp} value={cfg.hotspots.count}
            onChange={(e) => setCfg({ ...cfg, hotspots: { ...cfg.hotspots, count: parseInt(e.target.value, 10) || 0 } })} />
        </Field>
        <Field label="Always-review globs (one per line)">
          <textarea className={`${inp} h-20 font-mono text-xs`} value={cfg.hotspots.extra.join("\n")}
            onChange={(e) => setCfg({ ...cfg, hotspots: { ...cfg.hotspots, extra: e.target.value.split("\n").filter(Boolean) } })} />
        </Field>
      </Section>

      <Section title="Weekly drift">
        <Field label="Cron schedule (repo TZ)">
          <input className={inp} value={cfg.weekly.schedule}
            onChange={(e) => setCfg({ ...cfg, weekly: { ...cfg.weekly, schedule: e.target.value } })} />
        </Field>
        <Field label="Auto-promote HEAD to baseline after report">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={cfg.weekly.auto_promote_baseline}
              onChange={(e) => setCfg({ ...cfg, weekly: { ...cfg.weekly, auto_promote_baseline: e.target.checked } })} />
            enabled
          </label>
        </Field>
      </Section>

      <div className="mt-8 flex items-center gap-3">
        <button onClick={save} className="rounded bg-emerald-600 px-5 py-2 text-sm font-medium hover:bg-emerald-500">Save</button>
        {saved && <span className="text-xs text-emerald-400">saved ✓</span>}
      </div>
    </main>
  );
}

const inp = "w-full rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-sm uppercase tracking-wider text-neutral-500">{title}</h2>
      <div className="mt-3 space-y-4 rounded border border-neutral-800 p-4">{children}</div>
    </section>
  );
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-neutral-400">{label}</label>
      {children}
    </div>
  );
}

export default function Page() {
  return <Suspense fallback={<p className="p-8 text-sm text-neutral-500">Loading…</p>}><Inner /></Suspense>;
}
