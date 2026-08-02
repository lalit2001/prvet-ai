"use client";

import { Bot, PlayCircle, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Provider, type ProviderType } from "@/lib/api";
import {
  Button, Card, CardBody, CardHeader, Chip, EmptyState,
  Modal, PageHeader, useToast,
} from "@/components/ui";

const TYPES: { id: ProviderType; label: string; hint: string }[] = [
  { id: "openai", label: "OpenAI", hint: "api.openai.com" },
  { id: "anthropic", label: "Anthropic", hint: "api.anthropic.com" },
  { id: "azure_openai", label: "Azure OpenAI", hint: "your Azure endpoint + deployments" },
  { id: "bedrock", label: "AWS Bedrock", hint: "Claude/Titan/Llama on Bedrock" },
  { id: "vertex_ai", label: "Google Vertex AI", hint: "Gemini / PaLM on GCP" },
  { id: "ollama", label: "Ollama (local)", hint: "self-hosted, no key" },
  { id: "vllm", label: "vLLM (self-hosted)", hint: "any GPU-served OSS model" },
  { id: "litellm", label: "LiteLLM proxy", hint: "your own proxy" },
  { id: "openai_compatible", label: "Any OpenAI-compatible", hint: "custom base URL + key" },
];

const empty: Provider = {
  id: "", type: "openai", name: "", enabled: true, role_map: {},
};

export default function ProvidersPage() {
  const toast = useToast();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [draft, setDraft] = useState<Provider>(empty);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; latency_ms: number | null; error: string | null }>>({});

  async function refresh() { setProviders(await api.providers.list().catch(() => [])); }
  useEffect(() => { refresh(); }, []);

  function reset() { setDraft({ ...empty, id: crypto.randomUUID().slice(0, 12) }); }
  function openAdd() { reset(); setAddOpen(true); }

  async function save() {
    setBusy(true);
    try {
      // Update if exists, else add.
      const exists = providers.some(p => p.id === draft.id);
      if (exists) await api.providers.save(providers.map(p => p.id === draft.id ? draft : p));
      else await api.providers.add(draft);
      toast({ kind: "success", msg: `${exists ? "Updated" : "Added"} ${draft.name || draft.type}` });
      setAddOpen(false);
      refresh();
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
    finally { setBusy(false); }
  }

  async function del(id: string, name: string) {
    if (!confirm(`Delete provider "${name}"?`)) return;
    try { await api.providers.remove(id); toast({ kind: "success", msg: `Deleted ${name}` }); refresh(); }
    catch (e) { toast({ kind: "error", msg: String(e) }); }
  }

  async function test(p: Provider) {
    setTesting(p.id);
    try {
      const r = await api.providers.test(p.id);
      setResults(prev => ({ ...prev, [p.id]: { ok: r.ok, latency_ms: r.latency_ms, error: r.error } }));
      toast({ kind: r.ok ? "success" : "error",
              msg: r.ok ? `${p.name}: ok · ${r.latency_ms}ms` : `${p.name}: ${r.error}` });
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
    finally { setTesting(null); }
  }

  function edit(p: Provider) { setDraft(p); setAddOpen(true); }

  return (
    <>
      <PageHeader
        title="AI Providers"
        subtitle="Configure one or more LLM providers. Reviews route by role (fast / deep / embed) to the right one."
        actions={<Button onClick={openAdd}><Plus className="h-4 w-4" /> Add provider</Button>}
      />

      {providers.length === 0 ? (
        <EmptyState icon={Bot} title="No providers configured yet"
          hint="Add OpenAI, Anthropic, Bedrock, Azure OpenAI, Vertex AI, Ollama, vLLM, LiteLLM, or any OpenAI-compatible endpoint."
          action={<Button onClick={openAdd}><Plus className="h-4 w-4" /> Add your first provider</Button>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {providers.map(p => {
            const res = results[p.id];
            return (
              <Card key={p.id}>
                <CardHeader
                  title={p.name || p.type}
                  subtitle={TYPES.find(t => t.id === p.type)?.label || p.type}
                  action={
                    <div className="flex items-center gap-1">
                      {res && (
                        res.ok
                          ? <span className="text-[11px] text-emerald-400">ok · {res.latency_ms}ms</span>
                          : <span className="text-[11px] text-red-400 max-w-[160px] truncate" title={res.error ?? ""}>{res.error}</span>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => test(p)} disabled={testing === p.id}>
                        <PlayCircle className="h-3.5 w-3.5" /> {testing === p.id ? "…" : "Test"}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => edit(p)}>Edit</Button>
                      <Button variant="danger" size="sm" onClick={() => del(p.id, p.name)}><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  }
                />
                <CardBody className="space-y-2">
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(p.role_map).length === 0
                      ? <Chip className="text-yellow-300 border-yellow-900/60">no role_map — reviews can't route</Chip>
                      : Object.entries(p.role_map).map(([role, model]) => (
                        <Chip key={role}><span className="text-text-3">{role}</span>&nbsp;<span className="mono">{model}</span></Chip>
                      ))
                    }
                  </div>
                  <div className="text-[11px] text-text-3">
                    {p.enabled ? "enabled" : "disabled"} · {providerSummary(p)}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title={draft.name ? `Edit ${draft.name}` : "Add provider"} size="lg">
        <ProviderForm draft={draft} setDraft={setDraft} />
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button onClick={save} disabled={busy || !draft.name || !draft.type}>{busy ? "Saving…" : "Save"}</Button>
        </div>
      </Modal>
    </>
  );
}

function providerSummary(p: Provider): string {
  switch (p.type) {
    case "openai": return "api.openai.com";
    case "anthropic": return "api.anthropic.com";
    case "azure_openai": return p.endpoint || "no endpoint set";
    case "bedrock": return `region ${p.region || "us-east-1"}`;
    case "vertex_ai": return `${p.project || "no project"} / ${p.location || "us-central1"}`;
    case "ollama": return p.base_url || "http://localhost:11434";
    case "vllm":
    case "litellm":
    case "openai_compatible": return p.base_url || "no base_url set";
    default: return "";
  }
}

function ProviderForm({ draft, setDraft }: { draft: Provider; setDraft: (p: Provider) => void }) {
  const set = <K extends keyof Provider>(k: K, v: Provider[K]) => setDraft({ ...draft, [k]: v });
  const setRole = (role: string, model: string) => setDraft({ ...draft, role_map: { ...draft.role_map, [role]: model } });

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <F label="Provider type">
          <select value={draft.type} onChange={e => set("type", e.target.value as ProviderType)} className="w-full px-3 py-2 text-sm">
            {TYPES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
          <p className="mt-1 text-[11px] text-text-3">{TYPES.find(t => t.id === draft.type)?.hint}</p>
        </F>
        <F label="Display name">
          <input value={draft.name} onChange={e => set("name", e.target.value)} className="w-full px-3 py-2 text-sm" placeholder="e.g. Anthropic prod" required />
        </F>
      </div>

      <TypeSpecific draft={draft} set={set} />

      <div>
        <div className="mb-1 text-xs text-text-2">Role mapping</div>
        <div className="grid gap-2 md:grid-cols-3">
          <F label="Fast (triage, style, summary)">
            <input value={draft.role_map.fast || ""} onChange={e => setRole("fast", e.target.value)}
              placeholder={fastHint(draft.type)} className="w-full px-3 py-2 text-sm mono" />
          </F>
          <F label="Deep (security, bugs, blast radius)">
            <input value={draft.role_map.deep || ""} onChange={e => setRole("deep", e.target.value)}
              placeholder={deepHint(draft.type)} className="w-full px-3 py-2 text-sm mono" />
          </F>
          <F label="Embed (RAG, dedupe)">
            <input value={draft.role_map.embed || ""} onChange={e => setRole("embed", e.target.value)}
              placeholder={embedHint(draft.type)} className="w-full px-3 py-2 text-sm mono" />
          </F>
        </div>
        <p className="mt-1 text-[11px] text-text-3">Leave a role blank if this provider doesn't serve it — reviews will look for another provider that does.</p>
      </div>

      <div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.enabled} onChange={e => set("enabled", e.target.checked)} />
          Enabled
        </label>
      </div>
    </div>
  );
}

function TypeSpecific({ draft, set }: { draft: Provider; set: <K extends keyof Provider>(k: K, v: Provider[K]) => void }) {
  const t = draft.type;
  if (t === "openai" || t === "anthropic") {
    return <F label={`${t === "openai" ? "OpenAI" : "Anthropic"} API key`}>
      <input type="password" value={draft.api_key || ""} onChange={e => set("api_key", e.target.value)}
        className="w-full px-3 py-2 text-sm mono" placeholder="sk-..." />
    </F>;
  }
  if (t === "azure_openai") {
    return (<>
      <div className="grid gap-3 md:grid-cols-2">
        <F label="Endpoint"><input value={draft.endpoint || ""} onChange={e => set("endpoint", e.target.value)} placeholder="https://your-resource.openai.azure.com" className="w-full px-3 py-2 text-sm" /></F>
        <F label="API version"><input value={draft.api_version || ""} onChange={e => set("api_version", e.target.value)} placeholder="2024-06-01" className="w-full px-3 py-2 text-sm mono" /></F>
      </div>
      <F label="API key"><input type="password" value={draft.api_key || ""} onChange={e => set("api_key", e.target.value)} className="w-full px-3 py-2 text-sm mono" /></F>
      <p className="text-[11px] text-text-3">Role models below use the Azure <b>deployment name</b>, not the underlying model id.</p>
    </>);
  }
  if (t === "bedrock") {
    return (<>
      <div className="grid gap-3 md:grid-cols-2">
        <F label="Region"><input value={draft.region || ""} onChange={e => set("region", e.target.value)} placeholder="us-east-1" className="w-full px-3 py-2 text-sm mono" /></F>
        <F label="Access key ID"><input value={draft.access_key_id || ""} onChange={e => set("access_key_id", e.target.value)} className="w-full px-3 py-2 text-sm mono" /></F>
      </div>
      <F label="Secret access key"><input type="password" value={draft.secret_access_key || ""} onChange={e => set("secret_access_key", e.target.value)} className="w-full px-3 py-2 text-sm mono" /></F>
      <p className="text-[11px] text-text-3">For prod, prefer instance role / IRSA. Keys here are stored in the org config JSONB — move to Secrets Manager before going live.</p>
    </>);
  }
  if (t === "vertex_ai") {
    return (<>
      <div className="grid gap-3 md:grid-cols-2">
        <F label="Project ID"><input value={draft.project || ""} onChange={e => set("project", e.target.value)} className="w-full px-3 py-2 text-sm mono" /></F>
        <F label="Location"><input value={draft.location || ""} onChange={e => set("location", e.target.value)} placeholder="us-central1" className="w-full px-3 py-2 text-sm mono" /></F>
      </div>
      <F label="Service account JSON">
        <textarea value={draft.credentials_json || ""} onChange={e => set("credentials_json", e.target.value)}
          className="w-full px-3 py-2 text-xs mono h-32" placeholder='{ "type": "service_account", ... }' />
      </F>
    </>);
  }
  if (t === "ollama") {
    return <F label="Base URL"><input value={draft.base_url || ""} onChange={e => set("base_url", e.target.value)} placeholder="http://localhost:11434" className="w-full px-3 py-2 text-sm mono" /></F>;
  }
  // vllm / litellm / openai_compatible — all base_url + api_key
  return (<>
    <F label="Base URL"><input value={draft.base_url || ""} onChange={e => set("base_url", e.target.value)} placeholder="http://localhost:8000/v1" className="w-full px-3 py-2 text-sm mono" /></F>
    <F label="API key (optional)"><input type="password" value={draft.api_key || ""} onChange={e => set("api_key", e.target.value)} className="w-full px-3 py-2 text-sm mono" /></F>
  </>);
}

function F({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="mb-1 block text-xs text-text-2">{label}</label>{children}</div>;
}

function fastHint(t: ProviderType) {
  return {
    openai: "gpt-4o-mini", anthropic: "claude-haiku-4-5-20251001",
    azure_openai: "your-fast-deployment", bedrock: "anthropic.claude-3-5-haiku-20241022-v1:0",
    vertex_ai: "gemini-1.5-flash", ollama: "llama3.1:8b",
    vllm: "meta-llama/Llama-3.1-8B-Instruct", litellm: "gpt-4o-mini", openai_compatible: "your-model",
  }[t];
}
function deepHint(t: ProviderType) {
  return {
    openai: "gpt-4o", anthropic: "claude-sonnet-4-6",
    azure_openai: "your-deep-deployment", bedrock: "anthropic.claude-3-5-sonnet-20241022-v2:0",
    vertex_ai: "gemini-1.5-pro", ollama: "llama3.1:70b",
    vllm: "meta-llama/Llama-3.1-70B-Instruct", litellm: "claude-sonnet-4-6", openai_compatible: "your-model",
  }[t];
}
function embedHint(t: ProviderType) {
  return {
    openai: "text-embedding-3-small", anthropic: "",
    azure_openai: "your-embed-deployment", bedrock: "amazon.titan-embed-text-v2:0",
    vertex_ai: "textembedding-gecko@003", ollama: "nomic-embed-text",
    vllm: "BAAI/bge-large-en-v1.5", litellm: "text-embedding-3-small", openai_compatible: "",
  }[t];
}
