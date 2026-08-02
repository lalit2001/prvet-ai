"use client";

import clsx from "clsx";
import {
  AlertOctagon, CheckCircle2, ChevronDown, ChevronRight, Clock,
  FileCheck, FileText, Folder, FolderGit2, GitBranch, GitPullRequest, HelpCircle
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type Finding } from "@/lib/api";
import {
  Button, Card, CardBody, CardHeader, EmptyState, PageHeader,
  SeverityBadge, StatusPill, useToast
} from "@/components/ui";

type PullRequestDetail = {
  run_id: string;
  repo_id: string;
  repo_name: string;
  pr_number: number;
  commit_sha: string;
  title: string;
  source_branch: string;
  target_branch: string;
  created_at: string;
  findings: Finding[];
  files_tree: Record<string, Finding[]>;
  open_findings_count: number;
};

export default function PullRequestsPage() {
  const [prs, setPrs] = useState<PullRequestDetail[]>([]);
  const [selectedPrId, setSelectedPrId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const toast = useToast();

  async function loadPrs() {
    try {
      setLoading(true);
      const data = await api.prs.list();
      setPrs(data);
      if (data.length > 0 && !selectedPrId) {
        setSelectedPrId(data[0].run_id);
      }
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPrs();
  }, []);

  const selectedPr = useMemo(() => {
    return prs.find(p => p.run_id === selectedPrId) || null;
  }, [prs, selectedPrId]);

  // Build a tree structure of the files for the selected PR
  const fileNodes = useMemo(() => {
    if (!selectedPr) return [];
    const paths = Object.keys(selectedPr.files_tree);
    paths.sort();
    return paths;
  }, [selectedPr]);

  function toggleFile(path: string) {
    const next = new Set(expandedFiles);
    if (next.has(path)) {
      next.delete(path);
    } else {
      next.add(path);
    }
    setExpandedFiles(next);
  }

  async function handleFix(findingId: string) {
    try {
      setResolvingId(findingId);
      const nowStr = new Date().toISOString();
      await api.findings.resolve(findingId, {
        method: "pr_ui_fix",
        resolved_at: nowStr,
        note: "Fixed via open Pull Requests screen."
      });
      toast({
        kind: "success",
        msg: "Issue marked as fixed successfully!"
      });
      // Refresh findings and counts locally
      setPrs(prevPrs => {
        return prevPrs.map(pr => {
          if (pr.findings.some(f => f.id === findingId)) {
            const updatedFindings = pr.findings.map(f => {
              if (f.id === findingId) {
                return { ...f, status: "resolved" };
              }
              return f;
            });
            const updatedFilesTree: Record<string, Finding[]> = {};
            Object.entries(pr.files_tree).forEach(([file, list]) => {
              updatedFilesTree[file] = list.map(f => {
                if (f.id === findingId) {
                  return { ...f, status: "resolved" };
                }
                return f;
              });
            });
            const openCount = updatedFindings.filter(f => f.status === "open").length;
            return {
              ...pr,
              findings: updatedFindings,
              files_tree: updatedFilesTree,
              open_findings_count: openCount
            };
          }
          return pr;
        });
      });
    } catch (err) {
      toast({
        kind: "error",
        msg: `Failed to mark issue as fixed: ${err}`
      });
    } finally {
      setResolvingId(null);
    }
  }

  if (loading && prs.length === 0) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="text-center text-sm text-text-3">
          <Clock className="mx-auto h-6 w-6 animate-spin text-emerald-500" />
          <p className="mt-2">Loading pull requests...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        icon={AlertOctagon}
        title="Failed to load pull requests"
        hint={error}
        action={<Button onClick={loadPrs}>Try Again</Button>}
      />
    );
  }

  if (prs.length === 0) {
    return (
      <EmptyState
        icon={GitPullRequest}
        title="No pull requests found"
        hint="No review runs have been triggered for pull requests yet."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Pull Request Analysis" subtitle="Manage issues and code fixes per pull request" />

      <div className="grid gap-6 lg:grid-cols-4">
        {/* Master List: Left Column */}
        <div className="lg:col-span-1 space-y-3">
          <div className="text-xs uppercase tracking-wider text-text-3 font-semibold px-1">
            Open & Recent PRs ({prs.length})
          </div>
          <div className="space-y-2 overflow-y-auto max-h-[70vh] pr-1">
            {prs.map(pr => {
              const active = pr.run_id === selectedPrId;
              return (
                <button
                  key={pr.run_id}
                  onClick={() => {
                    setSelectedPrId(pr.run_id);
                    setExpandedFiles(new Set());
                  }}
                  className={clsx(
                    "w-full text-left p-3.5 rounded-lg border transition-all flex flex-col gap-2",
                    active
                      ? "border-emerald-500 bg-emerald-950/10 text-text-1 shadow-md shadow-emerald-900/5"
                      : "border-border bg-panel hover:bg-panel-2 hover:border-border-strong text-text-2"
                  )}
                >
                  <div className="flex items-start justify-between gap-2 w-full">
                    <span className="text-xs font-semibold text-text-3 tracking-tight truncate max-w-[120px]">
                      {pr.repo_name}
                    </span>
                    <StatusPill status={pr.open_findings_count > 0 ? "open" : "succeeded"} />
                  </div>
                  <div className="text-sm font-semibold leading-snug line-clamp-2">
                    {pr.title}
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-text-3 mt-1 w-full font-mono">
                    <span className="flex items-center gap-1">
                      <GitBranch className="h-3 w-3" />
                      PR #{pr.pr_number}
                    </span>
                    {pr.open_findings_count > 0 ? (
                      <span className="px-1.5 py-0.5 rounded bg-red-950/40 border border-red-900 text-red-300 font-bold tabular-nums">
                        {pr.open_findings_count} issues
                      </span>
                    ) : (
                      <span className="text-emerald-400 font-bold flex items-center gap-0.5">
                        <CheckCircle2 className="h-3 w-3" /> All clear
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Detailed Git View: Right Column */}
        <div className="lg:col-span-3">
          {selectedPr ? (
            <div className="space-y-6">
              {/* PR Header Card */}
              <Card className="border-border bg-panel/60 backdrop-blur">
                <CardBody className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <GitPullRequest className="h-5 w-5 text-emerald-400 shrink-0" />
                      <h2 className="text-lg font-bold text-text-1">{selectedPr.title}</h2>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-3 font-mono">
                      <span className="text-text-1 font-semibold">{selectedPr.repo_name}</span>
                      <span>·</span>
                      <span>PR #{selectedPr.pr_number}</span>
                      <span>·</span>
                      <span className="flex items-center gap-1 bg-panel px-2 py-0.5 rounded text-text-2 border border-border">
                        <code>{selectedPr.target_branch}</code>
                        <ChevronRight className="h-3 w-3" />
                        <code>{selectedPr.source_branch}</code>
                      </span>
                      <span>·</span>
                      <span>SHA {selectedPr.commit_sha.slice(0, 10)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Link
                      href={`/repo?id=${selectedPr.repo_id}`}
                      className="text-xs text-emerald-400 hover:underline border border-border bg-panel px-3 py-1.5 rounded-md hover:bg-panel-2 inline-flex items-center gap-1"
                    >
                      <FolderGit2 className="h-3.5 w-3.5" /> View Repo
                    </Link>
                  </div>
                </CardBody>
              </Card>

              {/* Git Structure Card */}
              <Card>
                <CardHeader
                  title="Files Tree & Findings"
                  subtitle="Modified files grouped with issues found in this pull request"
                />
                <CardBody className="p-0 divide-y divide-border">
                  {fileNodes.length === 0 ? (
                    <div className="p-10 text-center text-text-3">
                      <FileCheck className="mx-auto h-8 w-8 text-emerald-400 opacity-60" />
                      <p className="mt-2 text-sm text-text-1">No modified files or findings stored</p>
                    </div>
                  ) : (
                    fileNodes.map(filePath => {
                      const fileFindings = selectedPr.files_tree[filePath] || [];
                      const openFindings = fileFindings.filter(f => f.status === "open");
                      const expanded = expandedFiles.has(filePath);

                      return (
                        <div key={filePath} className="w-full">
                          {/* File row */}
                          <button
                            onClick={() => toggleFile(filePath)}
                            className="flex items-center justify-between w-full p-4 hover:bg-panel-2/50 text-left transition-colors font-mono text-xs"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              {expanded ? (
                                <ChevronDown className="h-4 w-4 text-text-3 shrink-0" />
                              ) : (
                                <ChevronRight className="h-4 w-4 text-text-3 shrink-0" />
                              )}
                              <FileText className="h-4 w-4 text-text-3 shrink-0" />
                              <span className="text-text-1 truncate">{filePath}</span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              {openFindings.length > 0 ? (
                                <span className="px-2 py-0.5 rounded bg-red-950/40 border border-red-900 text-red-300 font-bold font-sans">
                                  {openFindings.length} open
                                </span>
                              ) : (
                                <span className="text-emerald-400 font-bold font-sans flex items-center gap-0.5">
                                  <CheckCircle2 className="h-3.5 w-3.5" /> resolved
                                </span>
                              )}
                            </div>
                          </button>

                          {/* Collapsible findings inside the file */}
                          {expanded && (
                            <div className="bg-[#0c0d10] border-t border-border px-4 py-3 space-y-4">
                              {fileFindings.map(finding => {
                                const resolved = finding.status === "resolved";
                                return (
                                  <div
                                    key={finding.id}
                                    className={clsx(
                                      "border rounded-lg p-4 space-y-3 shadow-md",
                                      resolved
                                        ? "border-emerald-950 bg-emerald-950/5"
                                        : "border-border bg-panel"
                                    )}
                                  >
                                    <div className="flex items-start justify-between gap-3 flex-wrap">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <SeverityBadge severity={finding.severity} />
                                        <span className="text-[10px] uppercase tracking-wider text-text-3">
                                          {finding.category}
                                        </span>
                                        <StatusPill status={finding.status} />
                                      </div>
                                      <div className="text-[11px] text-text-3 font-mono">
                                        Line {finding.start_line || "–"}
                                      </div>
                                    </div>

                                    <div>
                                      <h4 className="text-sm font-semibold text-text-1">
                                        <Link
                                          href={`/findings/${finding.id}`}
                                          className="text-text-1 hover:text-emerald-400 hover:underline"
                                        >
                                          {finding.title}
                                        </Link>
                                      </h4>
                                      <p className="text-xs text-text-2 mt-1 leading-relaxed whitespace-pre-wrap">
                                        {finding.body}
                                      </p>
                                    </div>

                                    {finding.suggested_patch && !resolved && (
                                      <div className="mt-2 space-y-1">
                                        <div className="text-[10px] uppercase tracking-wider text-text-3 font-mono">
                                          Suggested Fix Diff
                                        </div>
                                        <div className="bg-[#07080a] border border-border p-2 rounded overflow-x-auto">
                                          <pre className="text-[10px] font-mono text-text-2 leading-4">
                                            {finding.suggested_patch.split("\n").map((line: string, idx: number) => {
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
                                      <div className="flex justify-end pt-2">
                                        <Button
                                          size="sm"
                                          onClick={() => handleFix(finding.id)}
                                          disabled={resolvingId !== null}
                                        >
                                          <CheckCircle2 className="h-3 w-3" />
                                          {resolvingId === finding.id ? "Fixing..." : "Fix Issue"}
                                        </Button>
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </CardBody>
              </Card>
            </div>
          ) : (
            <EmptyState
              icon={GitPullRequest}
              title="No Pull Request Selected"
              hint="Pick a Pull Request from the left sidebar to view its code structure and findings."
            />
          )}
        </div>
      </div>
    </div>
  );
}
