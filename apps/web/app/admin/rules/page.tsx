"use client";

import { useEffect, useState } from "react";
import { Sparkles, Trash2, Edit2, Loader2 } from "lucide-react";
import { api, type CustomRule, type OrgConfig } from "@/lib/api";

const LANGS = ["python", "typescript", "javascript", "java", "go", "csharp", "ruby", "php", "rust", "kotlin", "c", "cpp"];
const SEV = ["critical", "high", "medium", "low", "info"];
const CAT = ["security", "bug", "performance", "maintainability", "style", "dependency", "test"];

const inp = "w-full rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-600 focus:outline-none focus:border-emerald-600";
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

  // AI Rule Generator State
  const [aiDesc, setAiDesc] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    api.config.getOrg().then(setCfg).catch((e) => setError(String(e)));
  }, []);

  if (error && !cfg) return <pre className="m-8 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-300">{error}</pre>;
  if (!cfg) return <p className="p-8 text-sm text-neutral-500">Loading…</p>;

  async function persist(next: CustomRule[]) {
    if (!cfg) return;
    setError(null);
    try {
      const updated = await api.config.putOrg({ ...cfg, custom_rules: next });
      setCfg(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e) {
      setError(String(e));
    }
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
    setDraft(empty);
    setEditing(null);
  }

  async function deleteRule(id: string) {
    if (!cfg) return;
    if (!confirm(`Delete rule ${id}?`)) return;
    await persist(cfg.custom_rules.filter((r) => r.id !== id));
  }

  function loadForEdit(r: CustomRule) {
    setDraft(r);
    setEditing(r.id);
  }

  async function handleAiGenerate() {
    if (!aiDesc.trim()) return;
    setAiLoading(true);
    setError(null);
    try {
      const generated = await api.admin.generateRule(aiDesc, draft.language);
      if (generated) {
        setDraft({
          id: generated.id || `custom-${Date.now()}`,
          language: draft.language,
          severity: generated.severity || "medium",
          category: generated.category || "bug",
          message: generated.message || "",
          pattern: generated.pattern || "",
          pattern_not: generated.pattern_not || undefined,
          fix: generated.fix || undefined,
          enabled: true
        });
        setAiDesc("");
      }
    } catch (e) {
      setError(`AI Generation Failed: ${e}`);
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Custom rules</h1>
        <p className="mt-1 text-xs text-neutral-500">
          Stored in <code>organizations.settings.custom_rules</code>. Schema: <code>packages/rules/custom-rule.schema.json</code>.
        </p>
      </div>

      {error && (
        <pre className="rounded border border-red-900 bg-red-950/20 p-3 text-xs text-red-300">
          {error}
        </pre>
      )}

      {/* AI Assistant Card */}
      <section className="rounded-xl border border-emerald-950 bg-emerald-950/5 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-emerald-400" />
          <h2 className="text-sm font-bold text-emerald-300 uppercase tracking-wider">AI Rule Auto-fill Assistant</h2>
        </div>
        <p className="text-xs text-neutral-400">
          Describe what you want to check in natural language (e.g. <i>"Find calls to eval($code) that are not inside test files"</i>) and AI will write the rule pattern and metadata for you!
        </p>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-600 focus:outline-none focus:border-emerald-600"
            placeholder="Describe your target rule..."
            value={aiDesc}
            onChange={e => setAiDesc(e.target.value)}
            disabled={aiLoading}
          />
          <button
            onClick={handleAiGenerate}
            disabled={aiLoading || !aiDesc.trim()}
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-semibold hover:bg-emerald-500 flex items-center gap-2 disabled:opacity-40 disabled:hover:bg-emerald-600"
          >
            {aiLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Auto-fill
              </>
            )}
          </button>
        </div>
      </section>

      {/* Rule Form */}
      <section className="rounded-xl border border-neutral-800 bg-[#090a0f] p-5 space-y-4">
        <h2 className="text-xs uppercase tracking-wider text-neutral-400 font-bold border-b border-neutral-800 pb-2">
          {editing ? `Editing Rule: ${editing}` : "Configure Rule"}
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          <F label="Rule ID (kebab-case)">
            <input className={inp} value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} placeholder="no-print-in-prod" />
          </F>
          <F label="Target Language">
            <select className={inp} value={draft.language} onChange={(e) => setDraft({ ...draft, language: e.target.value })}>
              {LANGS.map((l) => <option key={l}>{l}</option>)}
            </select>
          </F>
          <F label="Severity">
            <select className={inp} value={draft.severity} onChange={(e) => setDraft({ ...draft, severity: e.target.value })}>
              {SEV.map((s) => <option key={s}>{s}</option>)}
            </select>
          </F>
          <F label="Category">
            <select className={inp} value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
              {CAT.map((c) => <option key={c}>{c}</option>)}
            </select>
          </F>
          <F label="Warning message to developers">
            <input className={inp} value={draft.message} onChange={(e) => setDraft({ ...draft, message: e.target.value })} placeholder="Do not use eval in production" />
          </F>
          <F label="Status">
            <label className="flex items-center gap-2 text-xs text-neutral-300 cursor-pointer mt-3">
              <input type="checkbox" checked={!!draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} className="accent-emerald-500" />
              <span>Enable this rule</span>
            </label>
          </F>
        </div>

        <F label="Pattern (semgrep-style, tree-sitter query, or regex)">
          <textarea className={`${inp} h-24 font-mono text-xs`} value={draft.pattern} onChange={(e) => setDraft({ ...draft, pattern: e.target.value })} placeholder="print($X)" />
        </F>
        <F label="pattern_not (optional exclusion)">
          <textarea className={`${inp} h-16 font-mono text-xs`} value={draft.pattern_not ?? ""} onChange={(e) => setDraft({ ...draft, pattern_not: e.target.value || undefined })} placeholder="print('debug mode')" />
        </F>
        <F label="fix (optional replacement)">
          <textarea className={`${inp} h-16 font-mono text-xs`} value={draft.fix ?? ""} onChange={(e) => setDraft({ ...draft, fix: e.target.value || undefined })} placeholder="logger.info($X)" />
        </F>

        <div className="mt-4 flex gap-3 pt-2">
          <button onClick={submitDraft} className="rounded bg-emerald-600 px-5 py-2 text-sm font-semibold hover:bg-emerald-500">
            {editing ? "Update Rule" : "Add Rule"}
          </button>
          {editing && (
            <button onClick={() => { setDraft(empty); setEditing(null); }} className="rounded border border-neutral-700 px-5 py-2 text-sm text-neutral-300 hover:bg-neutral-900">
              Cancel
            </button>
          )}
          {saved && <span className="self-center text-xs text-emerald-400 font-semibold">saved ✓</span>}
        </div>
      </section>

      {/* Rules List */}
      <section className="space-y-3">
        <h2 className="text-xs uppercase tracking-wider text-neutral-400 font-bold">
          Active Custom Rules ({cfg.custom_rules.length})
        </h2>
        {cfg.custom_rules.length === 0 ? (
          <p className="text-sm text-neutral-500">No custom rules configured yet.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {cfg.custom_rules.map((r) => (
              <div key={r.id} className="flex flex-col justify-between rounded-xl border border-neutral-800 bg-[#090a0f] p-4 space-y-4 hover:border-neutral-700 transition-colors">
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-neutral-500 font-mono">
                    <span>{r.language} · {r.category}</span>
                    <span className={r.enabled === false ? "text-red-400" : "text-emerald-400"}>
                      {r.enabled === false ? "Disabled" : r.severity}
                    </span>
                  </div>
                  <div>
                    <div className="font-mono text-sm text-neutral-100 font-bold">{r.id}</div>
                    <div className="mt-1 text-xs text-neutral-300">{r.message}</div>
                  </div>
                  <pre className="p-2 rounded bg-neutral-950 border border-neutral-900 font-mono text-[10px] text-neutral-500 overflow-x-auto">
                    {r.pattern}
                  </pre>
                </div>
                <div className="flex gap-2 justify-end border-t border-neutral-900 pt-3">
                  <button onClick={() => loadForEdit(r)} className="rounded border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-900 flex items-center gap-1.5">
                    <Edit2 className="h-3 w-3" /> Edit
                  </button>
                  <button onClick={() => deleteRule(r.id)} className="rounded border border-red-900/30 px-3 py-1.5 text-xs text-red-400 hover:bg-red-950/20 flex items-center gap-1.5">
                    <Trash2 className="h-3 w-3" /> Delete
                  </button>
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
    <div className="space-y-1.5">
      <label className="block text-xs font-semibold text-neutral-400">{label}</label>
      {children}
    </div>
  );
}
