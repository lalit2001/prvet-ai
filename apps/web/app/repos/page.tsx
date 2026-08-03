"use client";

import { FolderGit2, Plus, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type Repo } from "@/lib/api";
import {
  Button, Card, CardBody, EmptyState, Modal, PageHeader,
  TBody, TD, TH, THead, TR, Table, useToast,
} from "@/components/ui";

export default function ReposPage() {
  const toast = useToast();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [q, setQ] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try { setRepos(await api.repos.list()); }
    catch (e) { toast({ kind: "error", msg: String(e) }); }
  }
  useEffect(() => { refresh(); }, []);

  const filtered = useMemo(() => {
    const s = q.toLowerCase();
    return repos.filter(r => r.full_name.toLowerCase().includes(s) || r.clone_url.toLowerCase().includes(s));
  }, [repos, q]);

  async function addRepo(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.repos.createLocal(name, localPath);
      toast({ kind: "success", msg: `Added ${name}` });
      setName(""); setLocalPath(""); setAddOpen(false);
      refresh();
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
    finally { setBusy(false); }
  }

  async function deleteRepo(r: Repo) {
    if (!confirm(`Delete ${r.full_name}? This removes the repo and all its runs, baselines, and findings.`)) return;
    try {
      await api.repos.remove(r.id);
      toast({ kind: "success", msg: `Deleted ${r.full_name}` });
      refresh();
    } catch (e) { toast({ kind: "error", msg: String(e) }); }
  }

  return (
    <>
      <PageHeader
        title="Repositories"
        subtitle="Projects PRVet watches. Add a local path or a remote (soon)."
        actions={<Button onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" /> Add repo</Button>}
      />

      <Card>
        <div className="border-b border-border p-3">
          <div className="relative max-w-md">
            <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-text-3" />
            <input
              className="w-full py-1.5 pl-8 pr-3 text-sm"
              placeholder="Filter repos…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </div>
        <CardBody className="p-0">
          {filtered.length === 0 ? (
            <div className="p-8">
              <EmptyState icon={FolderGit2} title={q ? "No matches" : "No repositories yet"}
                hint={q ? "Adjust your filter." : "Add a local path to start reviewing."}
                action={!q && <Button onClick={() => setAddOpen(true)}><Plus className="h-4 w-4" /> Add repo</Button>} />
            </div>
          ) : (
            <Table>
              <THead>
                <TR><TH>Name</TH><TH>Source</TH><TH>Branch</TH><TH>Status</TH><TH></TH></TR>
              </THead>
              <TBody>
                {filtered.map((r) => (
                  <TR key={r.id}>
                    <TD className="font-medium">{r.full_name}</TD>
                    <TD className="mono text-xs text-text-3">{r.clone_url}</TD>
                    <TD className="mono text-xs text-text-3">{r.default_branch}</TD>
                    <TD>
                      <span className={r.is_enabled ? "text-emerald-400 text-xs" : "text-text-3 text-xs"}>
                        {r.is_enabled ? "enabled" : "disabled"}
                      </span>
                    </TD>
                    <TD className="text-right">
                      <div className="inline-flex items-center gap-2">
                        <Link href={`/repo?id=${r.id}`} className="text-emerald-400 hover:underline text-xs">Open →</Link>
                        <Button variant="danger" size="sm" onClick={() => deleteRepo(r)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add a repository">
        <form onSubmit={addRepo} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-text-2">Display name</label>
            <input className="w-full px-3 py-2 text-sm" value={name}
              onChange={(e) => setName(e.target.value)} placeholder="my-project" required />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-2">Local path (absolute)</label>
            <input className="w-full px-3 py-2 text-sm mono" value={localPath}
              onChange={(e) => setLocalPath(e.target.value)} placeholder="/Users/you/code/my-project" required />
            <p className="mt-1 text-[11px] text-text-3">Real forge connections (GitHub / GitLab / Azure DevOps) land in M3.</p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Adding…" : "Add"}</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
