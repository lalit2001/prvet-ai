"use client";

import { AlertOctagon, Bot, FolderGit2, GitFork, Network, Play, Radar } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, type Finding, type GraphSummary, type Provider, type Repo, type Run } from "@/lib/api";
import {
  Card, CardBody, CardHeader, EmptyState, PageHeader, SeverityBadge,
  StatCard, StatusPill, TBody, TD, TH, THead, TR, Table,
} from "@/components/ui";

const SEV_COLORS: Record<string, string> = {
  critical: "#f87171", high: "#fb923c", medium: "#facc15", low: "#60a5fa", info: "#94a3b8",
};

export default function Dashboard() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [findings, setFindings] = useState<Array<Finding & { repo: string; repo_id: string }>>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("all");
  const [graphs, setGraphs] = useState<Record<string, GraphSummary>>({});

  useEffect(() => {
    (async () => {
      const rs = await api.repos.list().catch(() => []);
      setRepos(rs);
      setRuns(await api.admin.runs().catch(() => []));
      setProviders(await api.providers.list().catch(() => []));
      const all = await Promise.all(rs.map(async r => {
        const fs = await api.repos.findings(r.id).catch(() => []);
        return fs.map(f => ({ ...f, repo: r.full_name, repo_id: r.id }));
      }));
      setFindings(all.flat());
      const gs = await Promise.all(rs.map(async r => [r.id, await api.graph.summary(r.id).catch(() => null)] as const));
      setGraphs(Object.fromEntries(gs.filter(([, g]) => g && g.symbols > 0) as Array<[string, GraphSummary]>));
    })();
  }, []);

  const graph = useMemo(() => {
    const ids = selectedRepo === "all" ? Object.keys(graphs) : [selectedRepo].filter(id => graphs[id]);
    if (ids.length === 0) return null;
    const name = (id: string) => repos.find(r => r.id === id)?.full_name.split("/").pop() ?? "";
    const sum = (k: "files" | "symbols" | "references" | "file_imports" | "resolved" | "unresolved") => ids.reduce((a, id) => a + (graphs[id][k] ?? 0), 0);
    const resolved = sum("resolved"), unresolved = sum("unresolved");
    return {
      files: sum("files"), symbols: sum("symbols"), references: sum("references"), file_imports: sum("file_imports"),
      rate: resolved + unresolved ? resolved / (resolved + unresolved) : null,
      topFiles: ids.flatMap(id => graphs[id].top_files.map(f => ({ ...f, repo_id: id, repo: name(id) }))).sort((a, b) => b.fan_in - a.fan_in).slice(0, 7),
      topSymbols: ids.flatMap(id => graphs[id].top_symbols.map(s => ({ ...s, repo_id: id, repo: name(id) }))).sort((a, b) => b.callers - a.callers).slice(0, 7),
      langs: Object.entries(ids.flatMap(id => graphs[id].by_language).reduce<Record<string, number>>((acc, l) => { acc[l.language] = (acc[l.language] || 0) + l.files; return acc; }, {})).sort((a, b) => b[1] - a[1]),
    };
  }, [graphs, selectedRepo, repos]);

  const scopedFindings = useMemo(() =>
    selectedRepo === "all" ? findings : findings.filter(f => f.repo_id === selectedRepo),
    [findings, selectedRepo]);
  const scopedRuns = useMemo(() =>
    selectedRepo === "all" ? runs : runs.filter(r => r.repo_id === selectedRepo),
    [runs, selectedRepo]);

  const sevDist = useMemo(() => {
    const c: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
    for (const f of scopedFindings) c[f.severity] = (c[f.severity] || 0) + 1;
    return Object.entries(c).filter(([, n]) => n > 0).map(([name, value]) => ({ name, value }));
  }, [scopedFindings]);

  const activity = useMemo(() => buildActivity(scopedRuns), [scopedRuns]);

  const openCount = scopedFindings.filter(f => f.status === "open").length;
  const failedRuns = scopedRuns.filter(r => r.status === "failed").length;

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Overview across repositories · scoped to the selected project"
        actions={
          <select value={selectedRepo} onChange={e => setSelectedRepo(e.target.value)}
            className="px-3 py-1.5 text-sm">
            <option value="all">All repositories</option>
            {repos.map(r => <option key={r.id} value={r.id}>{r.full_name}</option>)}
          </select>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={FolderGit2} label="Repositories" value={selectedRepo === "all" ? repos.length : 1}
          hint={selectedRepo === "all" ? `${repos.filter(r => r.is_enabled).length} enabled` : "scoped"} />
        <StatCard icon={AlertOctagon} label="Open findings" value={openCount}
          tone={openCount > 0 ? "warn" : "success"} hint={openCount > 0 ? "review below" : "all clear"} />
        <StatCard icon={Bot} label="AI providers" value={providers.length}
          hint={providers.length === 0 ? "add one to enable review" : `${providers.filter(p => p.enabled).length} enabled`}
          tone={providers.length === 0 ? "danger" : "success"} />
        <StatCard icon={Play} label="Runs" value={scopedRuns.length}
          hint={failedRuns ? `${failedRuns} failed` : "healthy"}
          tone={failedRuns ? "danger" : "success"} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Activity" subtitle="Runs over the last 14 days" />
          <CardBody className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={activity} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity={0.6} />
                    <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="day" fontSize={10} tick={{ fill: "#6b727c" }} axisLine={{ stroke: "#1f2328" }} tickLine={false} />
                <YAxis fontSize={10} tick={{ fill: "#6b727c" }} axisLine={false} tickLine={false} allowDecimals={false} width={24} />
                <Tooltip
                  contentStyle={{ background: "#101215", border: "1px solid #1f2328", borderRadius: 6, fontSize: 12 }}
                  labelStyle={{ color: "#a1a7b0" }}
                />
                <Area type="monotone" dataKey="runs" stroke="#10b981" fill="url(#g)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Severity distribution" subtitle="Open findings" />
          <CardBody className="flex h-56 flex-col">
            {sevDist.length === 0 ? (
              <div className="flex flex-1 items-center justify-center">
                <div className="text-center text-xs text-text-3">
                  <AlertOctagon className="mx-auto h-6 w-6 opacity-50" />
                  <p className="mt-2">No findings yet</p>
                </div>
              </div>
            ) : (
              <>
                <div className="flex-1">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={sevDist} dataKey="value" nameKey="name" innerRadius={38} outerRadius={68} paddingAngle={2}>
                        {sevDist.map(d => <Cell key={d.name} fill={SEV_COLORS[d.name] || "#6b7280"} />)}
                      </Pie>
                      <Tooltip contentStyle={{ background: "#101215", border: "1px solid #1f2328", borderRadius: 6, fontSize: 12 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-2 flex flex-wrap justify-center gap-2">
                  {sevDist.map(d => (
                    <span key={d.name} className="flex items-center gap-1 text-[11px]">
                      <span className="h-2 w-2 rounded-full" style={{ background: SEV_COLORS[d.name] }} />
                      <span className="text-text-2">{d.name}</span>
                      <span className="text-text-3">·</span>
                      <span className="tabular-nums text-text-1">{d.value}</span>
                    </span>
                  ))}
                </div>
              </>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-text-1">Code graph</h2>
            <p className="text-xs text-text-3">Symbols and cross-file links from the latest baseline — this is what blast-radius review is built on.</p>
          </div>
          <Link href={selectedRepo === "all" ? "/explorer" : `/explorer?repo=${selectedRepo}&pane=graph`} className="text-xs text-emerald-400 hover:underline">Open explorer →</Link>
        </div>
        {!graph ? (
          <Card><CardBody><EmptyState icon={Network} title="No graph indexed yet" hint="Run a baseline on a repository to build its symbol graph." /></CardBody></Card>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard icon={FolderGit2} label="Indexed files" value={graph.files}
                hint={graph.langs.map(([l, n]) => `${l} ${n}`).join(" · ") || "—"} />
              <StatCard icon={Network} label="Symbols" value={graph.symbols} hint="classes, functions, methods, types" />
              <StatCard icon={GitFork} label="References" value={graph.references} hint={`${graph.file_imports} file→file imports`} />
              <StatCard icon={Radar} label="Resolution" value={graph.rate === null ? "—" : `${Math.round(graph.rate * 100)}%`}
                hint="internal refs linked to a definition" tone={graph.rate !== null && graph.rate < 0.8 ? "warn" : "success"} />
            </div>
            <div className="mt-4 grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader title="Most depended-on files" subtitle="by number of importing files" />
                <CardBody className="p-0">
                  <ul className="divide-y divide-border">
                    {graph.topFiles.map(f => (
                      <li key={f.repo_id + f.path}>
                        <Link href={`/explorer?repo=${f.repo_id}&path=${encodeURIComponent(f.path)}`} className="flex items-center gap-3 px-4 py-2 hover:bg-panel-2">
                          <span className="mono truncate text-xs text-text-1">{f.path}</span>
                          <span className="ml-auto shrink-0 text-[10px] text-text-3">{f.language} · {f.loc} LOC</span>
                          <span className="shrink-0 rounded bg-emerald-950/60 px-1.5 text-[10px] tabular-nums text-emerald-400">{f.fan_in} importers</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader title="Most called symbols" subtitle="a change here has the widest blast radius" />
                <CardBody className="p-0">
                  <ul className="divide-y divide-border">
                    {graph.topSymbols.map(s => (
                      <li key={s.id}>
                        <Link href={`/explorer?repo=${s.repo_id}&symbol=${s.id}`} className="flex items-center gap-3 px-4 py-2 hover:bg-panel-2">
                          <span className="w-14 shrink-0 text-[10px] uppercase text-text-3">{s.kind}</span>
                          <span className="mono truncate text-xs text-text-1">{s.name}</span>
                          <span className="mono ml-auto truncate text-[10px] text-text-3">{s.path}:{s.start_line}</span>
                          <span className="shrink-0 rounded bg-emerald-950/60 px-1.5 text-[10px] tabular-nums text-emerald-400">{s.callers} callers</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
            </div>
          </>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Recent runs"
            action={<Link href="/runs" className="text-xs text-emerald-400 hover:underline">View all →</Link>} />
          <CardBody className="p-0">
            {scopedRuns.length === 0 ? (
              <div className="p-6"><EmptyState icon={Play} title="No runs" hint="Trigger a baseline or open a PR on an enabled repo." /></div>
            ) : (
              <Table>
                <THead><TR><TH>Repo</TH><TH>Type</TH><TH>Status</TH><TH>Commit</TH><TH>When</TH></TR></THead>
                <TBody>
                  {scopedRuns.slice(0, 8).map(r => (
                    <TR key={r.id}>
                      <TD className="max-w-[180px] truncate">{r.repo}</TD>
                      <TD className="text-text-2 text-xs">{r.run_type}</TD>
                      <TD><StatusPill status={r.status} /></TD>
                      <TD className="mono text-xs text-text-3">{(r.commit_sha || "").slice(0, 10)}</TD>
                      <TD className="text-text-3">{fmtWhen(r.created_at)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Top findings"
            action={<Link href="/findings" className="text-xs text-emerald-400 hover:underline">View all →</Link>} />
          <CardBody className="p-0">
            {scopedFindings.length === 0 ? (
              <div className="p-6"><EmptyState icon={AlertOctagon} title="Nothing to show" /></div>
            ) : (
              <ul className="divide-y divide-border">
                {scopedFindings.slice(0, 6).map(f => (
                  <li key={f.id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <SeverityBadge severity={f.severity} />
                      <span className="text-[10px] text-text-3">{f.category}</span>
                    </div>
                    <div className="mt-1 line-clamp-2 text-xs text-text-1">{f.title}</div>
                    <div className="mono mt-0.5 text-[10px] text-text-3 truncate">{f.repo}</div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      {providers.length === 0 && (
        <Card className="mt-6 border-yellow-900/60 bg-yellow-950/20">
          <CardBody>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-sm font-medium text-yellow-200">No AI providers configured</div>
                <p className="mt-1 text-xs text-yellow-300/70">Add at least one before reviews can run.</p>
              </div>
              <Link href="/admin/providers" className="shrink-0 rounded-md bg-yellow-600/20 px-3 py-1.5 text-xs font-medium text-yellow-200 hover:bg-yellow-600/30">Add provider →</Link>
            </div>
          </CardBody>
        </Card>
      )}
      {repos.length === 0 && (
        <Card className="mt-6 border-blue-900/60 bg-blue-950/20">
          <CardBody>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-sm font-medium text-blue-200">Getting started</div>
                <p className="mt-1 text-xs text-blue-300/70">Connect a GitHub account to review real PRs — full walkthrough in the setup guide.</p>
              </div>
              <div className="flex gap-2">
                <Link href="/admin/forges" className="rounded-md bg-blue-600/20 px-3 py-1.5 text-xs font-medium text-blue-200 hover:bg-blue-600/30">Connect GitHub</Link>
                <Link href="/help" className="rounded-md border border-blue-900/60 px-3 py-1.5 text-xs font-medium text-blue-200 hover:bg-blue-900/20">Setup guide</Link>
              </div>
            </div>
          </CardBody>
        </Card>
      )}
    </>
  );
}

function fmtWhen(iso: string) {
  try {
    const d = new Date(iso);
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return `${Math.floor(s)}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return d.toLocaleDateString();
  } catch { return iso; }
}

function buildActivity(runs: Run[]) {
  const bucket: Record<string, number> = {};
  const now = new Date();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(now); d.setDate(now.getDate() - i);
    bucket[d.toISOString().slice(0, 10)] = 0;
  }
  for (const r of runs) {
    const day = (r.created_at || "").slice(0, 10);
    if (day in bucket) bucket[day]++;
  }
  return Object.entries(bucket).map(([day, runs]) => ({ day: day.slice(5), runs }));
}
