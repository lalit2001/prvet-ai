"use client";

import { Cable, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { apiBaseUrl } from "@/lib/config";
import { Button, Card, CardBody, CardHeader, Chip, EmptyState, Modal, PageHeader, useToast } from "@/components/ui";

type Forge = {
  id: string; forge_type: string; display_name: string;
  base_url: string; github_user: string | null; status: string; created_at: string;
};
type Repo = { full_name: string; private: boolean; default_branch: string; language: string | null; updated_at: string };

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${apiBaseUrl()}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  const body = await r.text();
  if (!r.ok) throw new Error(`${r.status}: ${body.slice(0, 400)}`);
  return body ? JSON.parse(body) as T : ({} as T);
}

export default function ForgesPage() {
  const toast = useToast();
  const [forges, setForges] = useState<Forge[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState<Forge | null>(null);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [webhookBase, setWebhookBase] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() { setForges(await req<Forge[]>("/api/v1/forges").catch(() => [])); }
  useEffect(() => { refresh(); }, []);

  async function addForge(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await req("/api/v1/forges/github", { method: "POST", body: JSON.stringify({ token, name: name || undefined }) });
      toast({ kind: "success", msg: "GitHub connection added" });
      setAddOpen(false); setToken(""); setName("");
      refresh();
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
    finally { setBusy(false); }
  }

  async function openPicker(f: Forge) {
    setPickerOpen(f); setRepos([]); setSelected(null);
    try { setRepos(await req<Repo[]>(`/api/v1/forges/${f.id}/repos`)); }
    catch (e) { toast({ kind: "error", msg: String(e) }); }
  }

  async function enableRepo() {
    if (!pickerOpen || !selected) return;
    const url = webhookBase.replace(/\/$/, "") + `/api/v1/webhooks/${pickerOpen.id}`;
    setBusy(true);
    try {
      const out = await req<{ webhook_id: number | null }>(`/api/v1/forges/${pickerOpen.id}/repos/enable`,
        { method: "POST", body: JSON.stringify({ full_name: selected, webhook_url: url }) });
      toast({ kind: "success", msg: `Enabled ${selected}${out.webhook_id ? ` (webhook #${out.webhook_id})` : " (webhook may already exist)"}` });
      setPickerOpen(null);
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
    finally { setBusy(false); }
  }

  async function del(id: string) {
    if (!confirm("Delete this connection?")) return;
    try { await req(`/api/v1/forges/${id}`, { method: "DELETE" }); toast({ kind: "success", msg: "Deleted" }); refresh(); }
    catch (e) { toast({ kind: "error", msg: String(e) }); }
  }

  return (
    <>
      <PageHeader
        title="Forge connections"
        subtitle="Connect a GitHub account (PAT), enable repos, and Sentry Review will post reviews on new PRs."
        actions={<Button onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" /> Add GitHub</Button>}
      />

      {forges.length === 0 ? (
        <EmptyState icon={Cable} title="No forges connected"
          hint="Add a GitHub personal access token to start reviewing PRs. GitLab and Azure DevOps land in M4."
          action={<Button onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" /> Add GitHub</Button>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {forges.map(f => (
            <Card key={f.id}>
              <CardHeader
                title={f.display_name}
                subtitle={f.github_user ? `@${f.github_user}` : f.forge_type}
                action={
                  <div className="flex gap-1">
                    <Button variant="secondary" size="sm" onClick={() => openPicker(f)}>Enable a repo</Button>
                    <Button variant="danger" size="sm" onClick={() => del(f.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                }
              />
              <CardBody>
                <div className="flex items-center gap-2">
                  <Chip>{f.forge_type}</Chip>
                  <Chip>{f.status}</Chip>
                </div>
                <div className="mt-3 text-xs text-text-3 break-all">
                  Webhook URL for this connection:
                  <div className="mono mt-1 rounded border border-border bg-black/40 p-2 text-text-2 text-[11px]">
                    &lt;your-public-url&gt;/api/v1/webhooks/{f.id}
                  </div>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Connect GitHub" size="md">
        <form onSubmit={addForge} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-text-2">Display name (optional)</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full px-3 py-2 text-sm" placeholder="e.g. Work GitHub" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-2">GitHub personal access token</label>
            <input type="password" value={token} onChange={e => setToken(e.target.value)}
              className="w-full px-3 py-2 text-sm mono" placeholder="github_pat_… or ghp_…" required />
            <p className="mt-1 text-[11px] text-text-3">
              Needs: Contents (read), Pull requests (read/write), Webhooks (read/write). See <a href="/help" className="text-emerald-400 hover:underline">/help</a>.
            </p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Verifying…" : "Add"}</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!pickerOpen} onClose={() => setPickerOpen(null)} title="Enable a repository" size="lg">
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-text-2">Public webhook base URL (from ngrok or your deployment)</label>
            <input value={webhookBase} onChange={e => setWebhookBase(e.target.value)}
              className="w-full px-3 py-2 text-sm mono" placeholder="https://abc-123.ngrok-free.app" />
            <p className="mt-1 text-[11px] text-text-3">We'll register a webhook at <code className="mono">/api/v1/webhooks/&lt;connection_id&gt;</code>.</p>
          </div>
          <div className="max-h-96 overflow-y-auto rounded border border-border">
            {repos.length === 0 ? (
              <div className="p-6 text-center text-sm text-text-3">Loading repos…</div>
            ) : (
              <ul className="divide-y divide-border">
                {repos.map(r => (
                  <li key={r.full_name}>
                    <label className={`flex cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-panel-2/60 ${selected === r.full_name ? "bg-emerald-600/10" : ""}`}>
                      <input type="radio" name="repo" checked={selected === r.full_name} onChange={() => setSelected(r.full_name)} />
                      <div className="flex-1 min-w-0">
                        <div className="truncate text-text-1">{r.full_name}</div>
                        <div className="text-[11px] text-text-3">
                          {r.language ? r.language + " · " : ""}{r.default_branch}{r.private ? " · private" : ""}
                        </div>
                      </div>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPickerOpen(null)}>Cancel</Button>
            <Button onClick={enableRepo} disabled={!selected || !webhookBase || busy}>{busy ? "Enabling…" : "Enable"}</Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
