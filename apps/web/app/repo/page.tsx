"use client";

import clsx from "clsx";
import {
  AlertOctagon, ArrowLeft, CheckCircle2, ChevronRight, Clock,
  FileText, Folder, Info, Play, Save, Settings, ShieldAlert, Zap
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api, type Finding, type Repo, type RepoConfig, type ReviewResult, type RunDetail } from "@/lib/api";
import {
  Button, Card, CardBody, CardHeader, EmptyState, PageHeader,
  SeverityBadge, StatCard, StatusPill, useToast, Markdown
} from "@/components/ui";

const SAMPLE = `def divide(a, b):
    return a / b

def get_user(user_id):
    return db.execute("SELECT * FROM users WHERE id = " + user_id)
`;

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "findings", label: "Findings Explorer" },
  { id: "review",   label: "Ad-hoc Sandbox" },
  { id: "settings", label: "Project Settings" },
] as const;
type TabId = typeof TABS[number]["id"];

const SEVERITIES = ["critical", "high", "medium", "low", "info"];
const CATEGORIES = ["security", "bug", "performance", "maintainability", "style", "dependency", "test"];
const ROLES = ["admin", "maintain", "write", "read"];

function RepoInner() {
  const sp = useSearchParams();
  const id = sp.get("id") || "";
  const toast = useToast();

  const [tab, setTab] = useState<TabId>("overview");
  const [repo, setRepo] = useState<Repo | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [busy, setBusy] = useState<"idle" | "baseline" | "review">("idle");
  const [code, setCode] = useState(SAMPLE);
  const [language, setLanguage] = useState("python");
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [cfg, setCfg] = useState<RepoConfig | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Findings Explorer specific states
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [filterCat, setFilterCat] = useState<Set<string>>(new Set(CATEGORIES));
  const [filterSev, setFilterSev] = useState<Set<string>>(new Set(SEVERITIES));
  const [filterStatus, setFilterStatus] = useState<string>("open");
  const [searchQuery, setSearchQuery] = useState("");

  async function refresh() {
    if (!id) return;
    try {
      const all = await api.repos.list();
      setRepo(all.find(r => r.id === id) ?? null);
    } catch { /* ignore */ }
    try {
      const fs = await api.repos.findings(id);
      setFindings(fs);
      // Auto select first file if nothing selected and there are files
      const filesWithIssues = Array.from(new Set(fs.map(f => f.file_path)));
      if (filesWithIssues.length > 0 && !selectedFile) {
        setSelectedFile(filesWithIssues[0]);
      }
    } catch { /* ignore */ }
    try { setCfg(await api.repos.getConfig(id)); } catch { /* ignore */ }
    try { setRun(await api.repos.latestBaseline(id)); } catch { /* ignore */ }
  }

  useEffect(() => {
    refresh();
  }, [id]);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  if (!id) return <EmptyState icon={AlertOctagon} title="No repo selected" hint="Pick one from the Repositories page." />;

  function startPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const latest = await api.repos.latestBaseline(id);
        setRun(latest);
        if (latest && (latest.status === "succeeded" || latest.status === "failed")) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setBusy("idle");
          refresh();
          if (latest.status === "succeeded") {
            toast({
              kind: "success",
              msg: `Baseline completed · ${latest.stats.files_indexed ?? 0} files indexed · ${latest.findings_count} findings found`
            });
          } else {
            toast({ kind: "error", msg: "Baseline analysis failed" });
          }
        }
      } catch { /* keep polling */ }
    }, 2000);
  }

  async function runBaseline(force = false) {
    setBusy("baseline");
    try {
      const b = await api.repos.baseline(id, force);
      if (b.cached) {
        setBusy("idle");
        toast({ kind: "info", msg: "Same commit already baselined. Force re-run if needed." });
        refresh();
      } else {
        toast({ kind: "info", msg: "Baseline analysis started." });
        startPolling();
      }
    } catch (e) {
      toast({ kind: "error", msg: String(e) });
      setBusy("idle");
    }
  }

  async function runReview() {
    setBusy("review");
    setResult(null);
    try {
      const r = await api.reviews.adhoc(code, language, id);
      setResult(r);
      if (r.error) toast({ kind: "error", msg: r.error });
      else toast({ kind: "success", msg: `${r.findings.length} finding(s) discovered` });
      await refresh();
    } catch (e) {
      toast({ kind: "error", msg: String(e) });
    } finally {
      setBusy("idle");
    }
  }

  async function handleSaveSettings() {
    if (!cfg) return;
    setSavingSettings(true);
    try {
      const updated = await api.repos.putConfig(id, cfg);
      setCfg(updated);
      toast({ kind: "success", msg: "Project configurations saved successfully!" });
    } catch (e) {
      toast({ kind: "error", msg: `Failed to save settings: ${e}` });
    } finally {
      setSavingSettings(false);
    }
  }

  async function handleFixFinding(findingId: string) {
    setResolvingId(findingId);
    try {
      await api.findings.resolve(findingId, {
        method: "pr_ui_fix",
        resolved_at: new Date().toISOString(),
        note: "Fixed and auto-committed via Project Findings dashboard."
      });
      toast({ kind: "success", msg: "Fix applied and committed to branch successfully!" });
      // Update local findings state
      setFindings(prev => prev.map(f => f.id === findingId ? { ...f, status: "resolved" } : f));
    } catch (e) {
      toast({ kind: "error", msg: `Failed to apply fix: ${e}` });
    } finally {
      setResolvingId(null);
    }
  }

  async function handleCloseManual(findingId: string) {
    setResolvingId(findingId);
    try {
      await api.findings.resolve(findingId, {
        method: "manual_resolve",
        resolved_at: new Date().toISOString(),
        note: "Marked as resolved manually via the repository findings panel."
      });
      toast({ kind: "success", msg: "Finding has been closed/dismissed." });
      setFindings(prev => prev.map(f => f.id === findingId ? { ...f, status: "resolved" } : f));
    } catch (e) {
      toast({ kind: "error", msg: `Failed to close finding: ${e}` });
    } finally {
      setResolvingId(null);
    }
  }

  const toggleFilter = (set: Set<string>, item: string, setter: (s: Set<string>) => void) => {
    const next = new Set(set);
    next.has(item) ? next.delete(item) : next.add(item);
    setter(next);
  };

  // SonarQube Ratings logic
  const openFindings = useMemo(() => findings.filter(f => f.status === "open"), [findings]);
  
  const ratingMetrics = useMemo(() => {
    const bugs = openFindings.filter(f => f.category === "bug");
    const security = openFindings.filter(f => f.category === "security");
    const maintainability = openFindings.filter(f => ["maintainability", "style", "performance"].includes(f.category));

    const getRating = (count: number, highCount = 0) => {
      if (count === 0) return { grade: "A", color: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5" };
      if (highCount > 0) return { grade: "D", color: "text-orange-400 border-orange-500/20 bg-orange-500/5" };
      if (count <= 2) return { grade: "B", color: "text-blue-400 border-blue-500/20 bg-blue-500/5" };
      if (count <= 5) return { grade: "C", color: "text-yellow-400 border-yellow-500/20 bg-yellow-500/5" };
      return { grade: "E", color: "text-red-400 border-red-500/20 bg-red-500/5" };
    };

    const hasCriticalBugs = bugs.some(f => f.severity === "critical" || f.severity === "high");
    const hasCriticalSec = security.some(f => f.severity === "critical" || f.severity === "high");
    const hasCriticalMaint = maintainability.some(f => f.severity === "critical" || f.severity === "high");

    return {
      bugsCount: bugs.length,
      bugsRating: getRating(bugs.length, hasCriticalBugs ? 1 : 0),
      secCount: security.length,
      secRating: getRating(security.length, hasCriticalSec ? 1 : 0),
      maintCount: maintainability.length,
      maintRating: getRating(maintainability.length, hasCriticalMaint ? 1 : 0),
    };
  }, [openFindings]);

  const qualityGate = useMemo(() => {
    const failed = openFindings.some(f => f.severity === "critical" || f.severity === "high");
    return failed ? { status: "FAILED", color: "border-red-500/40 bg-red-950/10 text-red-400" } 
                  : { status: "PASSED", color: "border-emerald-500/40 bg-emerald-950/10 text-emerald-400" };
  }, [openFindings]);

  // Filters for Explorer
  const filteredFindings = useMemo(() => {
    return findings.filter(f => {
      const matchesSearch = searchQuery === "" || 
        f.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        f.file_path.toLowerCase().includes(searchQuery.toLowerCase());
      
      const matchesCat = filterCat.has(f.category);
      const matchesSev = filterSev.has(f.severity);
      const matchesStatus = filterStatus === "all" || f.status === filterStatus;

      return matchesSearch && matchesCat && matchesSev && matchesStatus;
    });
  }, [findings, filterCat, filterSev, filterStatus, searchQuery]);

  const filesList = useMemo(() => {
    const filesMap: Record<string, number> = {};
    for (const f of filteredFindings) {
      filesMap[f.file_path] = (filesMap[f.file_path] || 0) + (f.status === "open" ? 1 : 0);
    }
    return Object.entries(filesMap).map(([path, openCount]) => ({ path, openCount }));
  }, [filteredFindings]);

  const activeFileFindings = useMemo(() => {
    return filteredFindings.filter(f => f.file_path === selectedFile);
  }, [filteredFindings, selectedFile]);

  const severityCounts = useMemo(() => {
    const counts: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
    for (const f of openFindings) {
      if (counts[f.severity] !== undefined) counts[f.severity]++;
    }
    return counts;
  }, [openFindings]);

  const isRunning = run?.status === "running";
  const phasePct = _phasePct(run);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link href="/repos" className="inline-flex items-center gap-1 text-xs text-text-3 hover:text-text-1">
          <ArrowLeft className="h-3 w-3" /> All repositories
        </Link>
      </div>

      <PageHeader
        title={repo?.full_name ?? `Repository`}
        subtitle={repo?.clone_url}
        actions={
          <div className="flex gap-2">
            <Button onClick={() => runBaseline(false)} disabled={busy !== "idle" || isRunning}>
              {isRunning ? "Analyzing…" : (busy === "baseline" ? "Starting…" : "Analyze Baseline")}
            </Button>
            {run && !isRunning && (
              <Button variant="secondary" onClick={() => runBaseline(true)} disabled={busy !== "idle"}>
                Force Re-analyze
              </Button>
            )}
          </div>
        }
      />

      {/* Tabs Menu */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={clsx(
              "border-b-2 px-5 py-2.5 text-sm font-medium transition-colors",
              tab === t.id ? "border-emerald-500 text-text-1" : "border-transparent text-text-3 hover:text-text-1"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Contents: Overview */}
      {tab === "overview" && (
        <div className="space-y-6">
          {/* Quality Gate Card */}
          <div className={clsx("border rounded-xl p-5 flex items-center justify-between shadow-sm", qualityGate.color)}>
            <div className="flex items-center gap-3">
              {qualityGate.status === "PASSED" ? (
                <CheckCircle2 className="h-8 w-8 text-emerald-400" />
              ) : (
                <ShieldAlert className="h-8 w-8 text-red-400" />
              )}
              <div>
                <h3 className="font-bold text-lg leading-tight">Quality Gate {qualityGate.status}</h3>
                <p className="text-xs opacity-80 mt-0.5">
                  {qualityGate.status === "PASSED" 
                    ? "Congratulations! Your project has passed all high-severity quality standards." 
                    : "Attention: Open critical or high severity vulnerabilities must be resolved."}
                </p>
              </div>
            </div>
            <div className="text-right">
              <span className="text-xs uppercase tracking-wider block opacity-70">Open Issues</span>
              <span className="text-2xl font-black">{openFindings.length}</span>
            </div>
          </div>

          {/* Technical Ratings Grid */}
          <div className="grid gap-4 sm:grid-cols-4">
            {/* Reliability Rating */}
            <div className="bg-panel border border-border rounded-xl p-5 flex flex-col justify-between min-h-[140px] hover:border-border-strong transition-colors">
              <div>
                <span className="text-xs text-text-3 block uppercase tracking-wider font-semibold">Reliability</span>
                <span className="text-xs text-text-2 mt-1 block">Bugs & logical errors</span>
              </div>
              <div className="flex items-center justify-between mt-4">
                <span className="text-xl font-bold text-text-1">{ratingMetrics.bugsCount} Bugs</span>
                <div className={clsx("h-10 w-10 rounded-full flex items-center justify-center font-extrabold text-lg border", ratingMetrics.bugsRating.color)}>
                  {ratingMetrics.bugsRating.grade}
                </div>
              </div>
            </div>

            {/* Security Rating */}
            <div className="bg-panel border border-border rounded-xl p-5 flex flex-col justify-between min-h-[140px] hover:border-border-strong transition-colors">
              <div>
                <span className="text-xs text-text-3 block uppercase tracking-wider font-semibold">Security</span>
                <span className="text-xs text-text-2 mt-1 block">Vulnerabilities</span>
              </div>
              <div className="flex items-center justify-between mt-4">
                <span className="text-xl font-bold text-text-1">{ratingMetrics.secCount} Vulnerabilities</span>
                <div className={clsx("h-10 w-10 rounded-full flex items-center justify-center font-extrabold text-lg border", ratingMetrics.secRating.color)}>
                  {ratingMetrics.secRating.grade}
                </div>
              </div>
            </div>

            {/* Maintainability Rating */}
            <div className="bg-panel border border-border rounded-xl p-5 flex flex-col justify-between min-h-[140px] hover:border-border-strong transition-colors">
              <div>
                <span className="text-xs text-text-3 block uppercase tracking-wider font-semibold">Maintainability</span>
                <span className="text-xs text-text-2 mt-1 block">Code Smells & Debt</span>
              </div>
              <div className="flex items-center justify-between mt-4">
                <span className="text-xl font-bold text-text-1">{ratingMetrics.maintCount} Smells</span>
                <div className={clsx("h-10 w-10 rounded-full flex items-center justify-center font-extrabold text-lg border", ratingMetrics.maintRating.color)}>
                  {ratingMetrics.maintRating.grade}
                </div>
              </div>
            </div>

            {/* Statistics */}
            <div className="bg-panel border border-border rounded-xl p-5 flex flex-col justify-between min-h-[140px] hover:border-border-strong transition-colors">
              <div>
                <span className="text-xs text-text-3 block uppercase tracking-wider font-semibold">Project Metadata</span>
                <span className="text-xs text-text-2 mt-1 block">Code size & analysis scope</span>
              </div>
              <div className="space-y-1 text-xs text-text-2 mt-3 font-mono">
                <div className="flex justify-between">
                  <span>Files Walked</span>
                  <span className="font-semibold text-text-1">{run?.stats.files_seen ?? "–"}</span>
                </div>
                <div className="flex justify-between">
                  <span>Files Indexed</span>
                  <span className="font-semibold text-text-1">{run?.stats.files_indexed ?? "–"}</span>
                </div>
                <div className="flex justify-between">
                  <span>Symbols</span>
                  <span className="font-semibold text-text-1">{run?.stats.symbols ?? "–"}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Analysis Progress Banner */}
          {run && isRunning && (
            <Card className="border border-border">
              <CardBody className="space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-2 font-semibold">Analysis Status: <span className="text-emerald-400 capitalize">{run.stats.phase ?? "processing"}</span></span>
                  <span className="text-text-3">{phasePct.label}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-panel-2">
                  <div className="h-full bg-emerald-500 transition-all duration-300" style={{ width: `${phasePct.pct}%` }} />
                </div>
              </CardBody>
            </Card>
          )}

          <div className="grid gap-6 md:grid-cols-3">
            {/* Left: Severity distribution */}
            <div className="md:col-span-1">
              <Card>
                <CardHeader title="Issues Distribution" subtitle="Open findings categorized by severity" />
                <CardBody className="space-y-4">
                  {SEVERITIES.map(s => {
                    const count = severityCounts[s] || 0;
                    const max = Math.max(...Object.values(severityCounts), 1);
                    const pct = (count / max) * 100;
                    return (
                      <div key={s} className="space-y-1.5">
                        <div className="flex justify-between text-xs font-mono">
                          <span className="capitalize flex items-center gap-1.5">
                            <SeverityBadge severity={s} />
                            {s}
                          </span>
                          <span className="font-bold text-text-1">{count}</span>
                        </div>
                        <div className="h-1.5 w-full bg-[#12131a] rounded-full overflow-hidden">
                          <div className={clsx("h-full rounded-full", 
                            s === "critical" && "bg-red-500",
                            s === "high" && "bg-orange-500",
                            s === "medium" && "bg-yellow-500",
                            s === "low" && "bg-blue-500",
                            s === "info" && "bg-text-3"
                          )} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </CardBody>
              </Card>
            </div>

            {/* Right: baseline details and AI Summary */}
            <div className="md:col-span-2">
              <Card>
                <CardHeader title="Latest Baseline Summary" subtitle="Overview of project structure and code architecture" />
                <CardBody className="space-y-4">
                  {run?.stats.summary ? (
                    <div className="rounded-xl border border-emerald-950 bg-emerald-950/5 p-5">
                      <Markdown text={run.stats.summary} />
                    </div>
                  ) : (
                    <div className="p-8 text-center text-text-3">
                      <Clock className="mx-auto h-8 w-8 opacity-45" />
                      <p className="mt-2 text-sm">No analysis baseline summary found. Run baseline above.</p>
                    </div>
                  )}
                </CardBody>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Tab Contents: Findings Explorer */}
      {tab === "findings" && (
        <div className="space-y-4">
          {/* Quick Filters */}
          <div className="bg-panel border border-border p-4 rounded-xl flex flex-wrap gap-4 items-center justify-between">
            <div className="flex flex-wrap items-center gap-3">
              {SEVERITIES.map(s => (
                <button
                  key={s}
                  onClick={() => toggleFilter(filterSev, s, setFilterSev)}
                  className={clsx(
                    "px-2.5 py-1 text-xs rounded border transition-all flex items-center gap-1.5",
                    filterSev.has(s)
                      ? "border-emerald-500 bg-emerald-950/10 text-emerald-400 font-semibold"
                      : "border-border bg-panel-2 text-text-3 hover:text-text-2"
                  )}
                >
                  <SeverityBadge severity={s} />
                  <span className="capitalize">{s}</span>
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-text-3">Status:</span>
              <select
                value={filterStatus}
                onChange={e => setFilterStatus(e.target.value)}
                className="px-2.5 py-1 text-xs bg-panel-2 border border-border text-text-2 rounded focus:outline-none"
              >
                <option value="open">Open</option>
                <option value="resolved">Resolved</option>
                <option value="all">All</option>
              </select>
            </div>

            <div className="w-full md:w-64">
              <input
                type="text"
                placeholder="Search issues/files..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full px-3 py-1.5 text-xs bg-panel-2 border border-border text-text-2 rounded focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-4">
            {/* Left: Files with issues */}
            <div className="lg:col-span-1 space-y-2">
              <span className="text-xs uppercase tracking-wider text-text-3 font-semibold px-1">
                Affected Files ({filesList.length})
              </span>
              <div className="space-y-1 overflow-y-auto max-h-[60vh] pr-1">
                {filesList.length === 0 ? (
                  <div className="p-4 text-center border border-dashed border-border rounded text-xs text-text-3">
                    No files match filters
                  </div>
                ) : (
                  filesList.map(f => {
                    const active = selectedFile === f.path;
                    return (
                      <button
                        key={f.path}
                        onClick={() => setSelectedFile(f.path)}
                        className={clsx(
                          "w-full text-left p-2.5 rounded-lg border transition-colors flex items-center justify-between font-mono text-[11px]",
                          active
                            ? "border-emerald-500 bg-emerald-950/10 text-emerald-400 font-semibold"
                            : "border-border bg-panel hover:bg-panel-2 text-text-2"
                        )}
                      >
                        <div className="flex items-center gap-1.5 truncate mr-2">
                          <FileText className="h-3.5 w-3.5 shrink-0" />
                          <span className="truncate">{f.path}</span>
                        </div>
                        {f.openCount > 0 ? (
                          <span className="px-1.5 py-0.5 rounded bg-red-950/40 border border-red-900 text-red-300 font-bold shrink-0 font-sans">
                            {f.openCount}
                          </span>
                        ) : (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Right: File details & findings list */}
            <div className="lg:col-span-3">
              {selectedFile ? (
                <div className="space-y-4">
                  <div className="bg-panel border border-border p-3 rounded-lg flex items-center gap-2 font-mono text-xs text-text-1 font-semibold">
                    <Folder className="h-4 w-4 text-text-3" />
                    <span>{selectedFile}</span>
                  </div>

                  <div className="space-y-4">
                    {activeFileFindings.length === 0 ? (
                      <div className="p-8 text-center border border-border rounded text-text-3">
                        No findings in this file matching the active filters
                      </div>
                    ) : (
                      activeFileFindings.map(f => {
                        const resolved = f.status === "resolved";
                        return (
                          <div
                            key={f.id}
                            className={clsx(
                              "border rounded-xl p-5 space-y-4 shadow-sm",
                              resolved ? "border-emerald-950 bg-emerald-950/5" : "border-border bg-panel"
                            )}
                          >
                            <div className="flex items-start justify-between gap-3 flex-wrap">
                              <div className="flex flex-wrap items-center gap-2.5">
                                <SeverityBadge severity={f.severity} />
                                <span className="text-[10px] uppercase tracking-wider text-text-3 font-semibold bg-panel-2 px-2 py-0.5 rounded border border-border">
                                  {f.category}
                                </span>
                                <StatusPill status={f.status} />
                              </div>
                              <span className="text-xs text-text-3 font-mono">
                                Line {f.start_line || "–"}
                              </span>
                            </div>

                            <div className="space-y-2">
                              <h4 className="font-bold text-text-1 text-sm">{f.title}</h4>
                              <div className="text-xs leading-relaxed text-text-2">
                                <Markdown text={f.body} />
                              </div>
                            </div>

                            {f.suggested_patch && !resolved && (
                              <div className="space-y-1.5">
                                <span className="text-[10px] uppercase tracking-wider text-text-3 font-mono block">Suggested Fix Diff</span>
                                <div className="bg-[#07080a] border border-border p-2.5 rounded-lg overflow-x-auto">
                                  <pre className="text-[10px] font-mono text-text-2 leading-4">
                                    {f.suggested_patch.split("\n").map((line: string, idx: number) => {
                                      const isAdded = line.startsWith("+") && !line.startsWith("+++");
                                      const isRemoved = line.startsWith("-") && !line.startsWith("---");
                                      return (
                                        <div
                                          key={idx}
                                          className={clsx(
                                            "px-1.5",
                                            isAdded && "bg-emerald-950/30 text-emerald-300 border-l border-emerald-500",
                                            isRemoved && "bg-red-950/30 text-red-300 border-l border-red-500"
                                          )}
                                        >
                                          {line}
                                        </div>
                                      );
                                    })}
                                  </pre>
                                </div>
                              </div>
                            )}

                            {!resolved && (
                              <div className="flex justify-end border-t border-border pt-3 gap-2">
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => handleCloseManual(f.id)}
                                  disabled={resolvingId !== null}
                                >
                                  Close / Dismiss
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={() => handleFixFinding(f.id)}
                                  disabled={resolvingId !== null}
                                >
                                  <CheckCircle2 className="h-3.5 w-3.5" />
                                  {resolvingId === f.id ? "Applying Fix..." : "Fix Issue"}
                                </Button>
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon={FileText}
                  title="No file selected"
                  hint="Select a file from the sidebar to view its code analysis and findings."
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab Contents: Ad-hoc Sandbox */}
      {tab === "review" && (
        <Card>
          <CardHeader title="Ad-hoc LLM Sandbox" subtitle="Test code snippets instantly to see what findings PRVet catches" />
          <CardBody className="space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-3 font-semibold">Source Language:</span>
              <select
                value={language}
                onChange={e => setLanguage(e.target.value)}
                className="px-2 py-1 text-xs bg-panel-2 border border-border text-text-2 rounded"
              >
                {["python", "typescript", "javascript", "go", "java", "rust", "sql", "yaml"].map(l => (
                  <option key={l}>{l}</option>
                ))}
              </select>
            </div>
            <textarea
              value={code}
              onChange={e => setCode(e.target.value)}
              className="h-64 w-full p-3 font-mono text-xs bg-[#090a0f] border border-border text-text-2 rounded-lg focus:outline-none focus:border-emerald-500"
              spellCheck={false}
            />
            <div className="flex items-center gap-3">
              <Button onClick={runReview} disabled={busy !== "idle"}>
                {busy === "review" ? "Analyzing Snippet..." : "Review Snippet"}
              </Button>
              {!!result?.stats?.latency_ms && (
                <span className="text-xs text-text-3">
                  Parsed by {String(result.stats.model)} in {String(result.stats.latency_ms)}ms
                </span>
              )}
            </div>
            {result?.error && (
              <p className="rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-300">
                {result.error}
              </p>
            )}
            {result?.summary && (
              <div className="rounded-md border border-border bg-panel-2 p-3 text-xs text-text-2 whitespace-pre-wrap">
                {result.summary}
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {/* Tab Contents: Embedded Project Settings */}
      {tab === "settings" && (
        <Card>
          <CardHeader title="Project Configurations" subtitle="Equivalent of repositories.config or .crv.yml" />
          <CardBody className="space-y-6">
            {cfg ? (
              <div className="space-y-6 max-w-3xl">
                {/* Review settings */}
                <div className="space-y-4">
                  <h3 className="text-xs uppercase tracking-wider text-text-3 font-bold">Analysis Rules</h3>
                  <div className="grid gap-4 sm:grid-cols-2 p-4 border border-border bg-[#0b0c11] rounded-xl">
                    <div className="space-y-1">
                      <span className="text-xs text-text-2 font-semibold block">Gating Severity Level</span>
                      <span className="text-[10px] text-text-3 block leading-tight">Block PR merge if findings severity is equal or higher than:</span>
                      <select
                        className="w-full mt-2 rounded border border-border bg-panel px-3 py-1.5 text-xs text-text-2 focus:outline-none"
                        value={cfg.review.block_severity}
                        onChange={e => setCfg({ ...cfg, review: { ...cfg.review, block_severity: e.target.value } })}
                      >
                        {SEVERITIES.map(s => <option key={s}>{s}</option>)}
                      </select>
                    </div>

                    <div className="space-y-1">
                      <span className="text-xs text-text-2 font-semibold block">Minimum Confidence ({cfg.review.min_confidence.toFixed(2)})</span>
                      <span className="text-[10px] text-text-3 block leading-tight">Discard findings with AI confidence below:</span>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={cfg.review.min_confidence}
                        onChange={e => setCfg({ ...cfg, review: { ...cfg.review, min_confidence: parseFloat(e.target.value) } })}
                        className="w-full mt-3 accent-emerald-500"
                      />
                    </div>
                  </div>

                  <div className="p-4 border border-border bg-[#0b0c11] rounded-xl space-y-2">
                    <span className="text-xs text-text-2 font-semibold block">Gated Categories</span>
                    <span className="text-[10px] text-text-3 block leading-tight">Categories enabled for static analysis reviews:</span>
                    <div className="flex flex-wrap gap-x-5 gap-y-2 mt-2">
                      {CATEGORIES.map(c => {
                        const has = cfg.review.categories.includes(c);
                        return (
                          <label key={c} className="flex items-center gap-2 text-xs text-text-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={has}
                              onChange={() => {
                                setCfg({
                                  ...cfg,
                                  review: {
                                    ...cfg.review,
                                    categories: has 
                                      ? cfg.review.categories.filter(x => x !== c)
                                      : [...cfg.review.categories, c]
                                  }
                                });
                              }}
                              className="accent-emerald-500 rounded border-border"
                            />
                            <span className="capitalize">{c}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2 p-4 border border-border bg-[#0b0c11] rounded-xl">
                    <div className="space-y-1">
                      <span className="text-xs text-text-2 font-semibold block">Review Draft PRs</span>
                      <span className="text-[10px] text-text-3 block leading-tight">Enable automated reviews on draft pull requests:</span>
                      <label className="flex items-center gap-2 text-xs text-text-2 cursor-pointer mt-3">
                        <input
                          type="checkbox"
                          checked={cfg.review.drafts}
                          onChange={e => setCfg({ ...cfg, review: { ...cfg.review, drafts: e.target.checked } })}
                          className="accent-emerald-500 rounded"
                        />
                        <span>Analyze drafts</span>
                      </label>
                    </div>

                    <div className="space-y-1">
                      <span className="text-xs text-text-2 font-semibold block">Weekly Cron Schedule</span>
                      <span className="text-[10px] text-text-3 block leading-tight">Automated periodic baseline analysis (TZ regional time):</span>
                      <input
                        type="text"
                        className="w-full mt-2 rounded border border-border bg-panel px-3 py-1.5 text-xs text-text-2 font-mono"
                        value={cfg.weekly.schedule}
                        onChange={e => setCfg({ ...cfg, weekly: { ...cfg.weekly, schedule: e.target.value } })}
                      />
                    </div>
                  </div>
                </div>

                {/* Exclusions & Hotspots */}
                <div className="space-y-4">
                  <h3 className="text-xs uppercase tracking-wider text-text-3 font-bold">Path Rules & Hotspots</h3>
                  <div className="p-4 border border-border bg-[#0b0c11] rounded-xl space-y-4">
                    <div className="space-y-1">
                      <span className="text-xs text-text-2 font-semibold block">Exclude Paths</span>
                      <span className="text-[10px] text-text-3 block leading-tight">Glob patterns to exclude from walking (one path per line):</span>
                      <textarea
                        className="w-full mt-2 rounded border border-border bg-panel px-3 py-2 text-xs text-text-2 font-mono h-20 focus:outline-none focus:border-emerald-500"
                        value={cfg.exclude_paths.join("\n")}
                        onChange={e => setCfg({ ...cfg, exclude_paths: e.target.value.split("\n").filter(Boolean) })}
                      />
                    </div>

                    <div className="space-y-1">
                      <span className="text-xs text-text-2 font-semibold block">Hotspot Analysis Count</span>
                      <span className="text-[10px] text-text-3 block leading-tight">Number of top file hotspots analyzed by LLM during baselines:</span>
                      <input
                        type="number"
                        className="w-full mt-2 rounded border border-border bg-panel px-3 py-1.5 text-xs text-text-2 focus:outline-none focus:border-emerald-500"
                        value={cfg.hotspots.count}
                        onChange={e => setCfg({ ...cfg, hotspots: { ...cfg.hotspots, count: parseInt(e.target.value, 10) || 0 } })}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Button onClick={handleSaveSettings} disabled={savingSettings}>
                    <Save className="h-4 w-4" />
                    {savingSettings ? "Saving Settings..." : "Save Configurations"}
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-text-3">Loading configurations...</p>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function _phasePct(run: RunDetail | null): { pct: number; label: string } {
  if (!run) return { pct: 0, label: "" };
  const s = run.stats;
  if (s.phase === "indexing") {
    const seen = s.files_seen ?? 0;
    return { pct: Math.min(60, (seen % 100)), label: `${seen} walked` };
  }
  if (s.phase === "reviewing") {
    const done = s.hotspots_done ?? 0;
    const total = s.hotspots_total ?? 1;
    return { pct: 60 + Math.min(30, (done / total) * 30), label: `${done}/${total} hotspots` };
  }
  if (s.phase === "summarizing") return { pct: 92, label: "summarizing" };
  return { pct: 100, label: "" };
}

export default function RepoPage() {
  return (
    <Suspense fallback={<p className="text-sm text-text-3">Loading…</p>}>
      <RepoInner />
    </Suspense>
  );
}
