"use client";

import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Run } from "@/lib/api";
import { Card, CardBody, EmptyState, PageHeader, StatusPill, TBody, TD, TH, THead, TR, Table } from "@/components/ui";

export default function RunsPage() {
  const [rows, setRows] = useState<Run[]>([]);
  useEffect(() => { api.admin.runs().then(setRows).catch(() => {}); }, []);
  return (
    <>
      <PageHeader title="Runs" subtitle="All baseline / review / weekly runs, newest first" />
      <Card>
        <CardBody className="p-0">
          {rows.length === 0 ? (
            <div className="p-8"><EmptyState icon={Play} title="No runs yet" hint="Trigger a baseline from a repo detail page." /></div>
          ) : (
            <Table>
              <THead><TR><TH>Repo</TH><TH>Type</TH><TH>Status</TH><TH>Commit</TH><TH>Duration</TH><TH>Files</TH><TH>Symbols</TH><TH>When</TH></TR></THead>
              <TBody>
                {rows.map(r => {
                  const s = r.stats as Record<string, unknown>;
                  return (
                    <TR key={r.id}>
                      <TD>{r.repo}</TD>
                      <TD className="text-text-2 text-xs">{r.run_type}</TD>
                      <TD><StatusPill status={r.status} /></TD>
                      <TD className="mono text-xs text-text-3">{(r.commit_sha || "").slice(0, 10)}</TD>
                      <TD className="tabular-nums text-text-3">{r.duration_ms ? `${r.duration_ms}ms` : "–"}</TD>
                      <TD className="tabular-nums">{String(s?.files_indexed ?? "–")}</TD>
                      <TD className="tabular-nums">{String(s?.symbols ?? "–")}</TD>
                      <TD className="text-text-3">{r.created_at}</TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </>
  );
}
