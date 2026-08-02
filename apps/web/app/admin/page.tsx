"use client";

import { useEffect, useState } from "react";
import { api, type OrgConfig } from "@/lib/api";

const inp = "w-full rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm";
const SEVERITIES = ["critical", "high", "medium", "low", "info"];

export default function AdminPage() {
  const [cfg, setCfg] = useState<OrgConfig | null>(null);
  const [env, setEnv] = useState<Record<string, string | number> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; model: string; latency_ms: number | null; error: string | null } | null>(null);

  async function load() {
    try {
      setCfg(await api.config.getOrg());
      setEnv(await api.config.getEnv());
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => { load(); }, []);

  if (error) return <pre className="m-8 rounded border border-red-900 bg-red-950/30 p-3 text-xs text-red-300">{error}</pre>;
  if (!cfg || !env) return <p className="p-8 text-sm text-neutral-500">Loading…</p>;

  async function save() {
    if (!cfg) return;
    setError(null); setSaved(false);
    try {
      const updated = await api.config.putOrg(cfg);
      setCfg(updated); setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) { setError(String(e)); }
  }

  async function testLlm() {
    setTesting(true); setTestResult(null);
    try { setTestResult(await api.admin.llmTest()); }
    catch (e) { setTestResult({ ok: false, model: "?", latency_ms: null, error: String(e) }); }
    finally { setTesting(false); }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
      <p className="mt-1 text-xs text-neutral-500">Org-wide settings — stored in <code>organizations.settings</code>. Empty fields fall back to <code>.env</code>.</p>

      <section className="mt-8 rounded border border-neutral-800 p-4">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">LLM</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <F label={`Base URL (env: ${env.llm_base_url})`}>
            <input className={inp} value={cfg.llm.base_url} onChange={(e) => setCfg({ ...cfg, llm: { ...cfg.llm, base_url: e.target.value } })} placeholder={String(env.llm_base_url)} />
          </F>
          <F label={`API key ref (env: ${env.llm_api_key_ref})`}>
            <input className={inp} value={cfg.llm.api_key_ref} onChange={(e) => setCfg({ ...cfg, llm: { ...cfg.llm, api_key_ref: e.target.value } })} placeholder={String(env.llm_api_key_ref)} />
          </F>
          <F label={`Fast model (env: ${env.llm_model_fast})`}>
            <input className={inp} value={cfg.llm.model_fast} onChange={(e) => setCfg({ ...cfg, llm: { ...cfg.llm, model_fast: e.target.value } })} placeholder={String(env.llm_model_fast)} />
          </F>
          <F label={`Deep model (env: ${env.llm_model_deep})`}>
            <input className={inp} value={cfg.llm.model_deep} onChange={(e) => setCfg({ ...cfg, llm: { ...cfg.llm, model_deep: e.target.value } })} placeholder={String(env.llm_model_deep)} />
          </F>
          <F label="Monthly budget (USD)">
            <input type="number" className={inp} value={cfg.llm.monthly_budget_usd} onChange={(e) => setCfg({ ...cfg, llm: { ...cfg.llm, monthly_budget_usd: parseFloat(e.target.value) || 0 } })} />
          </F>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button onClick={testLlm} disabled={testing} className="rounded border border-neutral-700 px-3 py-1.5 text-xs hover:bg-neutral-900">{testing ? "testing…" : "Test connection"}</button>
          {testResult && (
            testResult.ok
              ? <span className="text-xs text-emerald-400">ok · {testResult.model} · {testResult.latency_ms}ms</span>
              : <span className="text-xs text-red-400">fail · {testResult.error}</span>
          )}
        </div>
      </section>

      <section className="mt-8 rounded border border-neutral-800 p-4">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">Gate defaults</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <F label={`Mode (env: ${env.gate_mode})`}>
            <select className={inp} value={cfg.gate.mode} onChange={(e) => setCfg({ ...cfg, gate: { ...cfg.gate, mode: e.target.value as "fail_open" | "fail_closed" } })}>
              <option value="fail_open">fail_open (LLM outage → neutral)</option>
              <option value="fail_closed">fail_closed (LLM outage → failure)</option>
            </select>
          </F>
          <F label={`Block severity floor (env: ${env.gate_block_severity})`}>
            <select className={inp} value={cfg.gate.block_severity} onChange={(e) => setCfg({ ...cfg, gate: { ...cfg.gate, block_severity: e.target.value as OrgConfig["gate"]["block_severity"] } })}>
              {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </F>
          <F label={`Min confidence (${cfg.gate.min_confidence.toFixed(2)}, env: ${env.min_confidence})`}>
            <input type="range" min={0} max={1} step={0.05} value={cfg.gate.min_confidence} onChange={(e) => setCfg({ ...cfg, gate: { ...cfg.gate, min_confidence: parseFloat(e.target.value) } })} className="w-full" />
          </F>
          <F label={`Max comments per PR (env: ${env.max_comments_per_pr})`}>
            <input type="number" className={inp} value={cfg.gate.max_comments_per_pr} onChange={(e) => setCfg({ ...cfg, gate: { ...cfg.gate, max_comments_per_pr: parseInt(e.target.value, 10) || 0 } })} />
          </F>
        </div>
      </section>

      <section className="mt-8 rounded border border-neutral-800 p-4">
        <h2 className="text-sm uppercase tracking-wider text-neutral-500">Deployment (read-only)</h2>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
          <KV k="deployment_mode" v={env.deployment_mode} />
          <KV k="queue_backend" v={env.queue_backend} />
          <KV k="storage_backend" v={env.storage_backend} />
          <KV k="secrets_backend" v={env.secrets_backend} />
        </div>
      </section>

      <div className="mt-8 flex items-center gap-3">
        <button onClick={save} className="rounded bg-emerald-600 px-5 py-2 text-sm font-medium hover:bg-emerald-500">Save org config</button>
        {saved && <span className="text-xs text-emerald-400">saved ✓</span>}
      </div>
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
function KV({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="rounded border border-neutral-800 bg-neutral-950 p-2">
      <div className="text-neutral-500">{k}</div>
      <div className="mt-0.5 font-mono text-neutral-200">{String(v)}</div>
    </div>
  );
}
