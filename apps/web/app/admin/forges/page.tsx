"use client";

import { Cable, Check, Pencil, Plus, Trash2, Server, AlertCircle, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { apiBaseUrl } from "@/lib/config";
import { Button, Card, CardBody, CardHeader, Chip, EmptyState, Modal, PageHeader, useToast } from "@/components/ui";

type Forge = {
  id: string; forge_type: string; display_name: string;
  base_url: string; github_user: string | null; gitlab_user: string | null;
  webhook_base_url: string | null; installation_id: string | null; app_uuid: string | null;
  account: string | null; repo_count: number;
  status: string; created_at: string;
};
type GhApp = { id: string; app_id: string; slug: string; name: string; html_url: string | null; status: string; installations: number; install_url: string | null };
type Repo = { full_name: string; private: boolean; default_branch: string; language: string | null; updated_at: string };

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  );
}

function GitlabIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m22 13.29-3.33-10a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.06.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18l-2.26 6.67H8.32L6.06 3.3a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.06.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18L2 13.29a.75.75 0 0 0 .07.65l8.33 6.1a.71.71 0 0 0 .81 0l8.33-6.1a.75.75 0 0 0 .07-.65z" />
    </svg>
  );
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("crv_token") : null;
  const r = await fetch(`${apiBaseUrl()}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init?.headers ?? {}) } });
  const body = await r.text();
  if (!r.ok) throw new Error(`${r.status}: ${body.slice(0, 400)}`);
  return body ? JSON.parse(body) as T : ({} as T);
}

export default function ForgesPage() {
  const toast = useToast();
  const [forges, setForges] = useState<Forge[]>([]);
  const [addType, setAddType] = useState<"github" | "gitlab" | "azure" | null>(null);
  const [pickerOpen, setPickerOpen] = useState<Forge | null>(null);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [customBaseUrl, setCustomBaseUrl] = useState("");
  const [webhookBase, setWebhookBase] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editingBaseFor, setEditingBaseFor] = useState<string | null>(null);
  const [editingBaseVal, setEditingBaseVal] = useState("");
  const [enableResult, setEnableResult] = useState<{ webhook_id: number | null; webhook_url: string } | null>(null);

  const [apps, setApps] = useState<GhApp[]>([]);
  const [appOrg, setAppOrg] = useState("");
  const [appBusy, setAppBusy] = useState(false);

  async function refresh() {
    setForges(await req<Forge[]>("/api/v1/forges").catch(() => []));
    setApps(await req<GhApp[]>("/api/v1/forges/github-apps").catch(() => []));
  }
  useEffect(() => {
    refresh();
    const sp = new URLSearchParams(window.location.search);
    if (sp.get("app") === "created") toast({ kind: "success", msg: `GitHub App "${sp.get("slug")}" registered — now install it on your repositories.` });
    if (sp.get("setup") === "github-app") toast({ kind: "success", msg: "Installation received — repositories are syncing." });
    if (sp.toString()) window.history.replaceState(null, "", window.location.pathname);
  }, []);

  async function registerApp() {
    setAppBusy(true);
    try {
      const m = await req<{ post_url: string; manifest: Record<string, unknown> }>(`/api/v1/forges/github-app/manifest${appOrg ? `?org=${encodeURIComponent(appOrg)}` : ""}`);
      // GitHub's manifest flow requires a real browser form POST
      const form = document.createElement("form");
      form.method = "POST"; form.action = m.post_url;
      const input = document.createElement("input");
      input.type = "hidden"; input.name = "manifest"; input.value = JSON.stringify(m.manifest);
      form.appendChild(input); document.body.appendChild(form); form.submit();
    } catch (e) { toast({ kind: "error", msg: String(e) }); setAppBusy(false); }
  }

  async function deleteApp(id: string) {
    if (!confirm("Remove this GitHub App registration? Installations stop receiving reviews.")) return;
    try { await req(`/api/v1/forges/github-apps/${id}`, { method: "DELETE" }); refresh(); }
    catch (e) { toast({ kind: "error", msg: String(e) }); }
  }

  async function handleAddForge(e: React.FormEvent) {
    e.preventDefault();
    if (!addType) return;
    setBusy(true);
    try {
      if (addType === "github") {
        await req("/api/v1/forges/github", { method: "POST", body: JSON.stringify({ token, name: name || undefined }) });
        toast({ kind: "success", msg: "GitHub connection added" });
      } else if (addType === "gitlab") {
        await req("/api/v1/forges/gitlab", { method: "POST", body: JSON.stringify({ token, base_url: customBaseUrl || undefined, name: name || undefined }) });
        toast({ kind: "success", msg: "GitLab connection added" });
      } else if (addType === "azure") {
        await req("/api/v1/forges/azure", { method: "POST", body: JSON.stringify({ token, base_url: customBaseUrl, name: name || undefined }) });
        toast({ kind: "success", msg: "Azure DevOps connection added" });
      }
      setAddType(null); setToken(""); setName(""); setCustomBaseUrl("");
      refresh();
    } catch (err) { toast({ kind: "error", msg: String(err) }); }
    finally { setBusy(false); }
  }

  async function openPicker(f: Forge) {
    setPickerOpen(f); setRepos([]); setSelected(null); setEnableResult(null);
    setWebhookBase(f.webhook_base_url || "");
    try { setRepos(await req<Repo[]>(`/api/v1/forges/${f.id}/repos`)); }
    catch (e) { toast({ kind: "error", msg: String(e) }); }
  }

  async function enableRepo() {
    if (!pickerOpen || !selected) return;
    const base = webhookBase.replace(/\/$/, "");
    const url = `${base}/api/v1/webhooks/${pickerOpen.id}`;
    setBusy(true);
    try {
      const out = await req<{ webhook_id: number | null; webhook_url: string }>(`/api/v1/forges/${pickerOpen.id}/repos/enable`,
        { method: "POST", body: JSON.stringify({ full_name: selected, webhook_url: url }) });
      
      if (pickerOpen.forge_type === "azure") {
        setEnableResult(out);
      } else {
        toast({ kind: "success", msg: `Enabled ${selected}${out.webhook_id ? ` (webhook #${out.webhook_id})` : " — webhook registered"}` });
        setPickerOpen(null);
      }
      refresh();
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
    finally { setBusy(false); }
  }

  async function saveBaseUrl(cid: string) {
    setBusy(true);
    try {
      await req(`/api/v1/forges/${cid}/webhook-base`,
        { method: "PUT", body: JSON.stringify({ webhook_base_url: editingBaseVal }) });
      toast({ kind: "success", msg: "Base URL saved" });
      setEditingBaseFor(null);
      refresh();
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
        title="Forge Connections"
        subtitle="Connect your GitHub, GitLab, or Azure DevOps instances, set your public webhook URL, and enable projects."
        actions={
          <div className="flex gap-2">
            <Button onClick={() => { setAddType("github"); setCustomBaseUrl(""); }} size="sm" variant="secondary">
              <GithubIcon className="h-4 w-4 mr-1.5" /> Connect GitHub
            </Button>
            <Button onClick={() => { setAddType("gitlab"); setCustomBaseUrl("https://gitlab.com"); }} size="sm" variant="secondary">
              <GitlabIcon className="h-4 w-4 mr-1.5" /> Connect GitLab
            </Button>
            <Button onClick={() => { setAddType("azure"); setCustomBaseUrl("https://dev.azure.com/"); }} size="sm" variant="secondary">
              <Server className="h-4 w-4 mr-1.5" /> Connect Azure DevOps
            </Button>
          </div>
        }
      />

      <Card className="mb-6 border border-purple-900/40 bg-purple-950/10">
        <CardHeader title="GitHub App" subtitle="Recommended: install PRVet as an app — no personal tokens, org-wide, one webhook, merge gate as a check run."
          action={
            <div className="flex items-center gap-2">
              <input value={appOrg} onChange={e => setAppOrg(e.target.value)} placeholder="org (blank = personal)"
                className="w-44 px-2 py-1.5 text-xs bg-panel border border-border rounded font-mono focus:outline-none" />
              <Button size="sm" onClick={registerApp} disabled={appBusy}>
                {appBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <><GithubIcon className="h-4 w-4 mr-1.5" /> Register app on GitHub</>}
              </Button>
            </div>
          } />
        <CardBody>
          {apps.length === 0 ? (
            <p className="text-xs text-text-3">
              Step 1 — <b>Register</b> creates the app in your GitHub account/org via the manifest flow (you approve on GitHub, then return here).
              Step 2 — <b>Install</b> it on the repositories you want reviewed. Installations appear below as connections.
              Requires <code className="font-mono">PUBLIC_URL</code> to be reachable by GitHub — in local dev run <code className="font-mono">ngrok http 8080</code>, put the https URL in <code className="font-mono">.env</code> as <code className="font-mono">PUBLIC_URL</code>, restart the API.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {apps.map(a => (
                <li key={a.id} className="flex items-center gap-3 py-2 text-xs">
                  <GithubIcon className="h-4 w-4 text-purple-400" />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-text-1">{a.name} <span className="font-mono text-text-3">· {a.slug}</span></div>
                    <div className="text-text-3">{a.installations} installation(s) · app id {a.app_id}</div>
                  </div>
                  {a.install_url && <a href={a.install_url} target="_blank" rel="noreferrer" className="rounded-md bg-emerald-600/20 px-3 py-1.5 font-medium text-emerald-300 hover:bg-emerald-600/30">Install on GitHub →</a>}
                  {a.html_url && <a href={a.html_url} target="_blank" rel="noreferrer" className="text-text-3 hover:text-text-1">settings</a>}
                  <Button variant="danger" size="sm" onClick={() => deleteApp(a.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {forges.length === 0 ? (
        <EmptyState
          icon={Cable}
          title="No forge connections configured"
          hint="Add a connection (PAT or instance token) to pull list of repositories and receive PR analysis webhooks."
        />
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {forges.map(f => (
            <Card key={f.id} className="border border-neutral-800 bg-[#0b0c10]/40">
              <CardHeader
                title={f.display_name}
                subtitle={
                  f.forge_type === "github" && f.github_user ? `@${f.github_user}` : 
                  f.forge_type === "gitlab" && f.gitlab_user ? `@${f.gitlab_user}` : 
                  f.base_url
                }
                action={
                  <div className="flex gap-1.5">
                    <Button variant="secondary" size="sm" onClick={() => openPicker(f)}>Enable repo</Button>
                    <Button variant="danger" size="sm" onClick={() => del(f.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                }
              />
              <CardBody className="space-y-4">
                <div className="flex items-center gap-2">
                  <Chip className={clsx(
                    f.forge_type === "github" ? "bg-purple-950/40 text-purple-400 border border-purple-800" :
                    f.forge_type === "gitlab" ? "bg-amber-950/40 text-amber-400 border border-amber-800" :
                    "bg-blue-950/40 text-blue-400 border border-blue-800"
                  )}>
                    {f.forge_type.toUpperCase()}
                  </Chip>
                  <Chip>{f.status}</Chip>
                  {f.installation_id && <Chip className="bg-emerald-950/40 text-emerald-400 border border-emerald-800">APP · {f.repo_count} repos</Chip>}
                </div>

                {f.installation_id ? (
                  <p className="text-xs text-text-3">Events arrive on the app-level webhook; enabled repositories sync automatically from the installation.</p>
                ) : (
                <div>
                  <div className="mb-1 flex items-center justify-between text-xs text-text-3">
                    <span>Public webhook base URL</span>
                    {editingBaseFor !== f.id && (
                      <button
                        onClick={() => { setEditingBaseFor(f.id); setEditingBaseVal(f.webhook_base_url || ""); }}
                        className="inline-flex items-center gap-1 text-text-3 hover:text-text-1 focus:outline-none"
                      ><Pencil className="h-3 w-3" /> {f.webhook_base_url ? "Change" : "Set"}</button>
                    )}
                  </div>
                  {editingBaseFor === f.id ? (
                    <div className="flex gap-2">
                      <input value={editingBaseVal} onChange={e => setEditingBaseVal(e.target.value)}
                        placeholder="https://abc.ngrok-free.app"
                        className="flex-1 px-3 py-1.5 text-xs bg-panel border border-border rounded focus:outline-none text-text-1 font-mono" />
                      <Button size="sm" onClick={() => saveBaseUrl(f.id)} disabled={busy}>
                        <Check className="h-3.5 w-3.5" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingBaseFor(null)}>Cancel</Button>
                    </div>
                  ) : (
                    <div className="mono rounded border border-border bg-black/40 p-2 text-[10px] text-text-2 break-all font-mono">
                      {f.webhook_base_url
                        ? `${f.webhook_base_url.replace(/\/$/, "")}/api/v1/webhooks/${f.id}`
                        : <span className="text-yellow-400">not set — configure base URL to accept payloads</span>}
                    </div>
                  )}
                </div>
                )}
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {/* Connect Modal */}
      <Modal
        open={addType !== null}
        onClose={() => setAddType(null)}
        title={addType ? `Connect ${addType === "github" ? "GitHub" : addType === "gitlab" ? "GitLab" : "Azure DevOps"}` : ""}
        size="md"
      >
        <form onSubmit={handleAddForge} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-text-2 font-semibold">Display Name (optional)</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full px-3 py-2 text-xs bg-panel-2 border border-border rounded focus:outline-none focus:border-emerald-600" placeholder="e.g. Production Forge" />
          </div>

          {(addType === "gitlab" || addType === "azure") && (
            <div>
              <label className="mb-1 block text-xs text-text-2 font-semibold">
                {addType === "gitlab" ? "GitLab Base URL" : "Azure DevOps Organization URL"}
              </label>
              <input
                value={customBaseUrl}
                onChange={e => setCustomBaseUrl(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-panel-2 border border-border rounded focus:outline-none focus:border-emerald-600 font-mono"
                placeholder={addType === "gitlab" ? "https://gitlab.com" : "https://dev.azure.com/my-org-name"}
                required
              />
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs text-text-2 font-semibold">Personal Access Token</label>
            <input type="password" value={token} onChange={e => setToken(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-panel-2 border border-border rounded focus:outline-none focus:border-emerald-600 font-mono" placeholder="Input token here" required />
            <p className="mt-1.5 text-[10px] text-neutral-500">
              Needs access scopes to read project repositories, files, and write code review comments.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="ghost" onClick={() => setAddType(null)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Verifying..." : "Add Connection"}</Button>
          </div>
        </form>
      </Modal>

      {/* Enable Repos Picker */}
      <Modal open={!!pickerOpen} onClose={() => setPickerOpen(null)} title={`Enable repo for ${pickerOpen?.display_name}`} size="lg">
        <div className="space-y-4">
          {!enableResult ? (
            <>
              <div>
                <label className="mb-1 block text-xs text-text-2 font-semibold">
                  Public Webhook Base URL (ngrok DSN or deployment address)
                </label>
                <input value={webhookBase} onChange={e => setWebhookBase(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-panel-2 border border-border rounded focus:outline-none focus:border-emerald-600 font-mono" placeholder="https://abc.ngrok-free.app" />
                <p className="mt-1 text-[10px] text-text-3 font-mono">
                  Payload URL: {webhookBase ? `${webhookBase.replace(/\/$/, "")}/api/v1/webhooks/${pickerOpen?.id}` : "Configure base above"}
                </p>
              </div>

              <div className="max-h-60 overflow-y-auto rounded-lg border border-border bg-panel-2/30 font-mono">
                {repos.length === 0 ? (
                  <div className="p-12 text-center text-xs text-text-3 flex items-center justify-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin text-emerald-500" /> Loading project list...
                  </div>
                ) : (
                  <ul className="divide-y divide-border">
                    {repos.map(r => (
                      <li key={r.full_name}>
                        <label className={`flex cursor-pointer items-center gap-3 px-4 py-2.5 text-xs hover:bg-panel-2/60 ${selected === r.full_name ? "bg-emerald-600/10" : ""}`}>
                          <input type="radio" name="repo" checked={selected === r.full_name} onChange={() => setSelected(r.full_name)} />
                          <div className="flex-1 min-w-0">
                            <div className="truncate text-text-1 font-semibold">{r.full_name}</div>
                            <div className="text-[10px] text-text-3 mt-0.5 font-sans">
                              {r.language ? r.language + " · " : ""}{r.default_branch}{r.private ? " · private" : ""}
                            </div>
                          </div>
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="flex justify-end gap-2 border-t border-border pt-4">
                <Button variant="ghost" onClick={() => setPickerOpen(null)}>Cancel</Button>
                <Button onClick={enableRepo} disabled={!selected || !webhookBase || busy}>{busy ? "Enabling..." : "Enable repository"}</Button>
              </div>
            </>
          ) : (
            // Success view for Azure DevOps / Manual Setup
            <div className="space-y-4">
              <div className="p-4 bg-emerald-950/20 border border-emerald-900 rounded-lg text-xs text-emerald-400 flex items-start gap-2">
                <Check className="h-4 w-4 shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-bold mb-1">Repository Enabled in Database!</h4>
                  <p>Repository "{selected}" has been created in the PRVet repository log.</p>
                </div>
              </div>

              <div className="p-4 bg-yellow-950/20 border border-yellow-900 rounded-lg text-xs text-yellow-400 space-y-2">
                <h4 className="font-bold flex items-center gap-1.5"><AlertCircle className="h-4 w-4" /> Manual Webhook Setup Required</h4>
                <p>Azure DevOps does not support programmatic webhook setup via PAT. You must configure the webhook service hook manually:</p>
                <ol className="list-decimal pl-5 space-y-1.5 mt-2">
                  <li>Go to your project settings in Azure DevOps.</li>
                  <li>Click on **Service Hooks** in the sidebar.</li>
                  <li>Create a new service hook of type **Web Hooks**.</li>
                  <li>Configure the trigger for: **Pull Request created**, **Pull Request updated**, and **Pull Request Commented**.</li>
                  <li>Paste the following Payload URL:</li>
                </ol>
                <div className="bg-black/60 border border-neutral-800 rounded p-2 text-[10px] font-mono select-all text-white break-all">
                  {enableResult.webhook_url}
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button onClick={() => setPickerOpen(null)}>Close</Button>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
