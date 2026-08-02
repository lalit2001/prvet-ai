"use client";

import clsx from "clsx";
import { AlertOctagon, ArrowLeft, CheckCircle2, Clock, FileText, Info, ShieldAlert, Zap } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Finding } from "@/lib/api";
import {
  Button, Card, CardBody, CardHeader, EmptyState, PageHeader,
  SeverityBadge, StatusPill, useToast, Markdown
} from "@/components/ui";

type FindingDetail = Finding & {
  repo_name: string;
  repo_id: string;
  suggested_patch: string | null;
  resolution: {
    method?: string;
    resolved_at?: string;
    commit?: string;
  } | null;
};

export default function FindingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const sp = useSearchParams();
  const id = (params?.id as string) || "";
  const toast = useToast();

  const [finding, setFinding] = useState<FindingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);

  // Return url can either be back to findings list or back to repo findings
  const fromRepo = sp.get("fromRepo");

  async function loadFinding() {
    if (!id) return;
    try {
      setLoading(true);
      const data = await api.findings.get(id);
      setFinding(data);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFinding();
  }, [id]);

  async function handleResolve() {
    if (!id) return;
    try {
      setResolving(true);
      const nowStr = new Date().toISOString();
      await api.findings.resolve(id, {
        method: "web_ui_resolve",
        resolved_at: nowStr,
        note: "Manually marked as resolved via the findings detail screen."
      });
      toast({
        kind: "success",
        msg: "Finding has been successfully resolved!"
      });
      loadFinding();
    } catch (err) {
      toast({
        kind: "error",
        msg: `Failed to resolve finding: ${err}`
      });
    } finally {
      setResolving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="text-center text-sm text-text-3">
          <Clock className="mx-auto h-6 w-6 animate-spin text-emerald-500" />
          <p className="mt-2">Loading issue details...</p>
        </div>
      </div>
    );
  }

  if (error || !finding) {
    return (
      <EmptyState
        icon={AlertOctagon}
        title="Failed to load finding"
        hint={error || "The requested issue could not be found."}
        action={
          <Button onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4" /> Go Back
          </Button>
        }
      />
    );
  }

  const isResolved = finding.status === "resolved";

  return (
    <div className="space-y-6">
      <div>
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-1.5 text-xs text-text-3 hover:text-text-1 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to list
        </button>
      </div>

      <PageHeader
        title={finding.title}
        subtitle={`Finding inside ${finding.repo_name}`}
        actions={
          !isResolved && (
            <Button onClick={handleResolve} disabled={resolving} className="gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {resolving ? "Resolving..." : "Mark as Resolved"}
            </Button>
          )
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left main info column */}
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader title="Description" subtitle="AI Code Review Summary" />
            <CardBody className="space-y-4">
              <div className="prose prose-invert max-w-none">
                <Markdown text={finding.body} />
              </div>
            </CardBody>
          </Card>

          {finding.suggested_patch && (
            <Card>
              <CardHeader title="Suggested Patch" subtitle="Recommended code modifications" />
              <CardBody className="p-0">
                <div className="bg-[#0b0c0f] overflow-x-auto p-4 border-t border-border">
                  <pre className="text-xs font-mono text-[#e7e9ec] leading-5">
                    {finding.suggested_patch.split("\n").map((line: string, idx: number) => {
                      const isAdded = line.startsWith("+") && !line.startsWith("+++");
                      const isRemoved = line.startsWith("-") && !line.startsWith("---");
                      return (
                        <div
                          key={idx}
                          className={clsx(
                            "px-2 py-0.5 rounded-sm",
                            isAdded && "bg-emerald-950/40 text-emerald-300 border-l-2 border-emerald-500",
                            isRemoved && "bg-red-950/40 text-red-300 border-l-2 border-red-500"
                          )}
                        >
                          {line}
                        </div>
                      );
                    })}
                  </pre>
                </div>
              </CardBody>
            </Card>
          )}
        </div>

        {/* Right sidebar metadata column */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Metadata" />
            <CardBody className="space-y-4">
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between py-1.5 border-b border-border">
                  <span className="text-text-3 text-xs">Status</span>
                  <StatusPill status={finding.status} />
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-border">
                  <span className="text-text-3 text-xs">Severity</span>
                  <SeverityBadge severity={finding.severity} />
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-border">
                  <span className="text-text-3 text-xs">Category</span>
                  <span className="text-text-1 capitalize">{finding.category}</span>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-border">
                  <span className="text-text-3 text-xs">Confidence</span>
                  <span className="text-text-1 font-mono">{Number(finding.confidence ?? 0).toFixed(2)}</span>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-border">
                  <span className="text-text-3 text-xs">Created At</span>
                  <span className="text-text-2 text-xs">
                    {new Date(finding.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between py-1.5 border-b border-border">
                  <span className="text-text-3 text-xs">Repository</span>
                  <Link
                    href={`/repo?id=${finding.repo_id}`}
                    className="text-emerald-400 hover:underline text-xs max-w-[150px] truncate"
                  >
                    {finding.repo_name}
                  </Link>
                </div>
                <div className="py-1.5">
                  <span className="text-text-3 text-xs block mb-1">File Location</span>
                  <div className="flex items-center gap-1.5 rounded bg-panel-2 border border-border px-2 py-1.5">
                    <FileText className="h-4 w-4 text-text-3 shrink-0" />
                    <span className="text-xs text-text-1 font-mono break-all">
                      {finding.file_path}
                      {finding.start_line ? `:${finding.start_line}` : ""}
                      {finding.end_line ? `-${finding.end_line}` : ""}
                    </span>
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>

          {isResolved && finding.resolution && (
            <Card className="border-emerald-900/60 bg-emerald-950/5">
              <CardHeader title="Resolution Details" />
              <CardBody className="space-y-3 text-xs">
                <div className="flex items-center gap-2 text-emerald-400 font-semibold mb-1">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Issue Resolved</span>
                </div>
                <div className="space-y-1.5 text-text-2">
                  <div>
                    <span className="text-text-3 font-medium">Method:</span>{" "}
                    <code className="bg-panel px-1.5 py-0.5 rounded text-[10px]">
                      {finding.resolution.method || "manual"}
                    </code>
                  </div>
                  {finding.resolution.resolved_at && (
                    <div>
                      <span className="text-text-3 font-medium">Resolved at:</span>{" "}
                      {new Date(finding.resolution.resolved_at).toLocaleString()}
                    </div>
                  )}
                  {finding.resolution.commit && (
                    <div>
                      <span className="text-text-3 font-medium">Commit SHA:</span>{" "}
                      <code className="text-emerald-300 font-mono">
                        {finding.resolution.commit.slice(0, 10)}
                      </code>
                    </div>
                  )}
                </div>
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
