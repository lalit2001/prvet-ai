"use client";

import { AlertOctagon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, type Finding, type Repo } from "@/lib/api";
import {
  Card, CardBody, Chip, EmptyState, PageHeader, SeverityBadge, StatusPill,
  TBody, TD, TH, THead, TR, Table,
} from "@/components/ui";

const SEVERITIES = ["critical", "high", "medium", "low", "info"];
const CATEGORIES = ["security", "bug", "performance", "maintainability", "style", "dependency", "test"];

export default function FindingsPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [findings, setFindings] = useState<Array<Finding & { repo: string }>>([]);
  const [sev, setSev] = useState<Set<string>>(new Set(SEVERITIES));
  const [cat, setCat] = useState<Set<string>>(new Set(CATEGORIES));
  const [q, setQ] = useState("");

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
      (!s || f.title.toLowerCase().includes(s) || f.body.toLowerCase().includes(s) || f.repo.toLowerCase().includes(s))
    );
  }, [findings, sev, cat, q]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of findings) c[f.severity] = (c[f.severity] || 0) + 1;
    return c;
  }, [findings]);

  const toggle = (set: Set<string>, s: Set<string>, val: string, setter: (x: Set<string>) => void) => {
    const next = new Set(s);
    next.has(val) ? next.delete(val) : next.add(val);
    setter(next);
  };

  return (
    <>
      <PageHeader title="Findings" subtitle={`${filtered.length} of ${findings.length} across ${repos.length} repos`} />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {SEVERITIES.map(s => (
          <button key={s} onClick={() => toggle(sev, sev, s, setSev)}
            className={sev.has(s) ? "" : "opacity-40"}>
            <span className="inline-flex items-center gap-1">
              <SeverityBadge severity={s} />
              <span className="text-[10px] text-text-3">{counts[s] || 0}</span>
            </span>
          </button>
        ))}
        <span className="mx-2 h-4 w-px bg-border" />
        {CATEGORIES.map(c => (
          <button key={c} onClick={() => toggle(cat, cat, c, setCat)}
            className={cat.has(c) ? "" : "opacity-40"}>
            <Chip>{c}</Chip>
          </button>
        ))}
        <div className="ml-auto">
          <input className="px-3 py-1.5 text-sm w-64" placeholder="Search title/body/repo…"
            value={q} onChange={e => setQ(e.target.value)} />
        </div>
      </div>

      <Card>
        <CardBody className="p-0">
          {filtered.length === 0 ? (
            <div className="p-8"><EmptyState icon={AlertOctagon} title="No findings match" hint="Adjust filters above." /></div>
          ) : (
            <Table>
              <THead><TR><TH>Severity</TH><TH>Category</TH><TH>Title</TH><TH>Repo</TH><TH>File</TH><TH>Conf</TH><TH>Status</TH></TR></THead>
              <TBody>
                {filtered.map(f => (
                  <TR key={f.id}>
                    <TD><SeverityBadge severity={f.severity} /></TD>
                    <TD className="text-text-2 text-xs">{f.category}</TD>
                    <TD className="max-w-[380px] truncate">{f.title}</TD>
                    <TD className="text-text-2 text-xs">{f.repo}</TD>
                    <TD className="mono text-xs text-text-3">{f.file_path === "adhoc" ? "–" : `${f.file_path}${f.start_line ? `:${f.start_line}` : ""}`}</TD>
                    <TD className="text-text-3 text-xs tabular-nums">{f.confidence.toFixed(2)}</TD>
                    <TD><StatusPill status={f.status} /></TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </>
  );
}
