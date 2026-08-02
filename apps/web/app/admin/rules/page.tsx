"use client";

import { useEffect, useState } from "react";
import { api, type CustomRule, type OrgConfig } from "@/lib/api";

const LANGS = ["python", "typescript", "javascript", "java", "go", "csharp", "ruby", "php", "rust", "kotlin", "c", "cpp"];
const SEV = ["critical", "high", "medium", "low", "info"];
const CAT = ["security", "bug", "performance", "maintainability", "style", "dependency", "test"];

const inp = "w-full rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm";
const empty: CustomRule = {
  id: "", language: "python", severity: "medium", category: "bug",
  message: "", pattern: "", enabled: true,
};

export default function RulesPage() {
  const [cfg, setCfg] = useState<OrgConfig | null>(null);
  const [draft, setDraft] = useState<CustomRule>(empty);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.config.getOrg().then(setCfg).catch((e) => setError(String(e))); }, []);

  if (error) return <pre className="m-8 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-300">{error}</pre>;
  if (!cfg) return <p className="p-8 text-sm text-neutral-500">Loading…</p>;

  async function persist(next: CustomRule[]) {
    if (!cfg) return;
    setError(null);
    try {
      const updated = await api.config.putOrg({ ...cfg, custom_rules: next });
      setCfg(updated); setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e) { setError(String(e)); }
  }

  function validate(r: CustomRule): string | null {
    if (!/^[a-z][a-z0-9_-]+$/.test(r.id)) return "id must match ^[a-z][a-z0-9_-]+$";
    if (!r.message) return "message required";
    if (!r.pattern) return "pattern required";
    return null;
  }

  async function submitDraft() {
    if (!cfg) return;
    const err = validate(draft);
    if (err) { setError(err); return; }
    const others = cfg.custom_rules.filter((r) => r.id !== draft.id);
    await persist([...others, draft]);
    setDraft(empty); setEditing(null);
  }

  async function deleteRule(id: string) {
    if (!cfg) return;
    if (!confirm(`Delete rule ${id}?`)) return;
    await persist(cfg.custom_rules.filter((r) => r.id !== id));
  }

  function loadForEdit(r: CustomRule) {
    setDraft(r); setEditing(r.id);
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Custom rules</h1>
      <p className="mt-1 text-xs text-neutral-500">Stored in <code>organizations.settings.custom_rules</code>. Schema: <code>packages/rules/custom-rule.schema.json</code>.</p>

      <section className="mt-8 rounded border border-neutral-800 p-4">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">{editing ? `Editing ${editing}` : "Add rule"}</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <F label="id (kebab-case)">
            <input className={inp} value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} placeholder="no-print-in-prod" />
          </F>
          <F label="language">
            <select className={inp} value={draft.language} onChange={(e) => setDraft({ ...draft, language: e.target.value })}>
              {LANGS.map((l) => <option key={l}>{l}</option>)}
            </select>
          </F>
          <F label="severity">
            <select className={inp} value={draft.severity} onChange={(e) => setDraft({ ...draft, severity: e.target.value })}>
              {SEV.map((s) => <option key={s}>{s}</option>)}
            </select>
          </F>
          <F label="category">
            <select className={inp} value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
              {CAT.map((c) => <option key={c}>{c}</option>)}
            </select>
          </F>
          <F label="message">
            <input className={inp} value={draft.message} onChange={(e) => setDraft({ ...draft, message: e.target.value })} />
          </F>
          <F label="enabled">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} /> enabled
            </label>
          </F>
        </div>
        <F label="pattern (semgrep-style, tree-sitter query, or regex)">
          <textarea className={`${inp} h-24 font-mono text-xs`} value={draft.pattern} onChange={(e) => setDraft({ ...draft, pattern: e.target.value })} placeholder="print($X)" />
        </F>
        <F label="pattern_not (optional exclusion)">
          <textarea className={`${inp} h-16 font-mono text-xs`} value={draft.pattern_not ?? ""} onChange={(e) => setDraft({ ...draft, pattern_not: e.target.value || undefined })} />
        </F>
        <F label="fix (optional replacement)">
          <textarea className={`${inp} h-16 font-mono text-xs`} value={draft.fix ?? ""} onChange={(e) => setDraft({ ...draft, fix: e.target.value || undefined })} />
        </F>
        <div className="mt-3 flex gap-3">
          <button onClick={submitDraft} className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500">{editing ? "Update" : "Add rule"}</button>
          {editing && <button onClick={() => { setDraft(empty); setEditing(null); }} className="rounded border border-neutral-700 px-4 py-2 text-sm hover:bg-neutral-900">Cancel</button>}
          {saved && <span className="self-center text-xs text-emerald-400">saved ✓</span>}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">Existing rules ({cfg.custom_rules.length})</h2>
        {cfg.custom_rules.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-500">No custom rules yet.</p>
        ) : (
          <div className="mt-3 space-y-2">
            {cfg.custom_rules.map((r) => (
              <div key={r.id} className="flex items-start justify-between gap-3 rounded border border-neutral-800 bg-neutral-950 p-3">
                <div>
                  <div className="text-xs text-neutral-500">{r.severity} · {r.category} · {r.language} {r.enabled === false ? "· disabled" : ""}</div>
                  <div className="mt-1 font-mono text-sm text-neutral-100">{r.id}</div>
                  <div className="mt-1 text-sm text-neutral-300">{r.message}</div>
                  <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs text-neutral-500">{r.pattern}</pre>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button onClick={() => loadForEdit(r)} className="rounded border border-neutral-700 px-2 py-1 text-xs hover:bg-neutral-900">edit</button>
                  <button onClick={() => deleteRule(r.id)} className="rounded border border-red-900 px-2 py-1 text-xs text-red-300 hover:bg-red-950/30">delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function F({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-neutral-400">{label}</label>
      {children}
    </div>
  );
}
