"use client";

import clsx from "clsx";
import { AlertOctagon, ChevronLeft, ChevronRight, Filter, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, type Finding, type Repo } from "@/lib/api";
import {
  Card, CardBody, Chip, EmptyState, PageHeader, SeverityBadge, StatusPill,
  TBody, TD, TH, THead, TR, Table, Button
} from "@/components/ui";

const SEVERITIES = ["critical", "high", "medium", "low", "info"];
const CATEGORIES = ["security", "bug", "performance", "maintainability", "style", "dependency", "test"];

export default function FindingsPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [findings, setFindings] = useState<Array<Finding & { repo: string }>>([]);
  const [sev, setSev] = useState<Set<string>>(new Set(SEVERITIES));
  const [cat, setCat] = useState<Set<string>>(new Set(CATEGORIES));
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("open");

  // Pagination states
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  useEffect(() => {
    (async () => {
      const rs = await api.repos.list().catch(() => []);
      setRepos(rs);
      const all = await Promise.all(rs.map(async r => {
        const fs = await api.repos.findings(r.id).catch(() => []);
        return fs.map(f => ({ ...f, repo: r.full_name }));
      }));
      setFindings(all.flat());
    })();
  }, []);

  const filtered = useMemo(() => {
    const s = q.toLowerCase();
    return findings.filter(f =>
      sev.has(f.severity) &&
      cat.has(f.category) &&
      (statusFilter === "all" || f.status === statusFilter) &&
      (!s || f.title.toLowerCase().includes(s) || f.body.toLowerCase().includes(s) || f.repo.toLowerCase().includes(s) || f.file_path.toLowerCase().includes(s))
    );
  }, [findings, sev, cat, statusFilter, q]);

  // Reset to first page when filters or search query change
  useEffect(() => {
    setCurrentPage(1);
  }, [sev, cat, statusFilter, q, pageSize]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of findings) c[f.severity] = (c[f.severity] || 0) + 1;
    return c;
  }, [findings]);

  // Calculate paginated subset
  const totalItems = filtered.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  
  const paginated = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, currentPage, pageSize]);

  const toggle = (set: Set<string>, val: string, setter: (x: Set<string>) => void) => {
    const next = new Set(set);
    next.has(val) ? next.delete(val) : next.add(val);
    setter(next);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Findings" subtitle={`${filtered.length} of ${findings.length} across ${repos.length} repos`} />

      {/* Filter and Search Bar */}
      <div className="bg-panel border border-border p-5 rounded-xl space-y-4 shadow-sm">
        {/* Row 1: Search & Status */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="relative flex-1">
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-3">
              <Search className="h-4 w-4" />
            </span>
            <input
              className="w-full pl-9 pr-4 py-2 text-xs bg-panel-2 border border-border text-text-2 rounded-lg focus:outline-none focus:border-emerald-500"
              placeholder="Search title, description, file, repo..."
              value={q}
              onChange={e => setQ(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <span className="text-xs text-text-3 font-semibold flex items-center gap-1.5">
              <Filter className="h-3.5 w-3.5" /> Status:
            </span>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="px-3 py-1.5 text-xs bg-panel-2 border border-border text-text-2 rounded-lg focus:outline-none"
            >
              <option value="open">Open Issues</option>
              <option value="resolved">Resolved</option>
              <option value="all">All</option>
            </select>
          </div>
        </div>

        {/* Row 2: Severities & Categories */}
        <div className="border-t border-border pt-4 flex flex-col md:flex-row md:items-center gap-4">
          {/* Severities */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider text-text-3 font-bold mr-1">Severity:</span>
            {SEVERITIES.map(s => (
              <button
                key={s}
                onClick={() => toggle(sev, s, setSev)}
                className={clsx(
                  "px-2.5 py-1 text-xs rounded border transition-all flex items-center gap-1.5",
                  sev.has(s)
                    ? "border-emerald-500 bg-emerald-950/10 text-emerald-400 font-semibold"
                    : "border-border bg-panel-2 text-text-3 hover:text-text-2"
                )}
              >
                <SeverityBadge severity={s} />
                <span className="text-[10px] text-text-3 font-mono font-bold">({counts[s] || 0})</span>
              </button>
            ))}
          </div>

          <span className="hidden md:inline h-4 w-px bg-border" />

          {/* Categories */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] uppercase tracking-wider text-text-3 font-bold mr-1">Category:</span>
            {CATEGORIES.map(c => {
              const active = cat.has(c);
              return (
                <button
                  key={c}
                  onClick={() => toggle(cat, c, setCat)}
                  className={clsx(
                    "px-2 py-0.5 text-[10px] capitalize font-medium rounded border transition-colors",
                    active
                      ? "border-emerald-500 bg-emerald-950/10 text-emerald-400 font-semibold"
                      : "border-border bg-panel-2 text-text-3 hover:text-text-2"
                  )}
                >
                  {c}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Findings Table */}
      <Card>
        <CardBody className="p-0">
          {paginated.length === 0 ? (
            <div className="p-12">
              <EmptyState
                icon={AlertOctagon}
                title="No findings match filters"
                hint="Adjust your search filters or status options above."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <THead>
                  <TR>
                    <TH>Severity</TH>
                    <TH>Category</TH>
                    <TH>Issue Title</TH>
                    <TH>Repository</TH>
                    <TH>File & Line</TH>
                    <TH>Confidence</TH>
                    <TH>Status</TH>
                  </TR>
                </THead>
                <TBody>
                  {paginated.map(f => (
                    <TR key={f.id} className="hover:bg-panel-2/50 transition-colors">
                      <TD><SeverityBadge severity={f.severity} /></TD>
                      <TD className="text-text-2 text-xs font-semibold capitalize">{f.category}</TD>
                      <TD className="max-w-[320px]">
                        <Link href={`/findings/${f.id}`} className="text-text-1 hover:text-emerald-400 font-medium hover:underline block truncate">
                          {f.title}
                        </Link>
                      </TD>
                      <TD className="text-text-2 text-xs font-mono truncate max-w-[140px]">{f.repo}</TD>
                      <TD className="mono text-xs text-text-3 truncate max-w-[200px]">
                        {f.file_path === "adhoc" ? "–" : `${f.file_path}${f.start_line ? `:${f.start_line}` : ""}`}
                      </TD>
                      <TD className="text-text-3 text-xs font-mono tabular-nums">{Number(f.confidence ?? 0.6).toFixed(2)}</TD>
                      <TD><StatusPill status={f.status} /></TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Pagination Footer */}
      {totalItems > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 px-1 py-2 text-xs text-text-3">
          <div className="flex items-center gap-2">
            <span>Show</span>
            <select
              value={pageSize}
              onChange={e => setPageSize(parseInt(e.target.value, 10))}
              className="px-2 py-1 bg-panel border border-border text-text-2 rounded focus:outline-none"
            >
              {[10, 20, 50, 100].map(sz => (
                <option key={sz} value={sz}>{sz} rows</option>
              ))}
            </select>
            <span>of {totalItems} findings</span>
          </div>

          <div className="flex items-center gap-2 font-medium">
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              className="p-1.5 rounded border border-border bg-panel hover:bg-panel-2 disabled:opacity-40 disabled:hover:bg-panel transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-3 font-semibold text-text-2">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              className="p-1.5 rounded border border-border bg-panel hover:bg-panel-2 disabled:opacity-40 disabled:hover:bg-panel transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
