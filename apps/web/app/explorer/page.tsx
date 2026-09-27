"use client";

import clsx from "clsx";
import {
  ArrowDownLeft, ArrowUpRight, Braces, ChevronDown, ChevronRight, Code2, Crosshair, FileText,
  GitFork, Loader2, Network, Radar, Search, X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { DependencyGraph } from "@/components/DependencyGraph";
import { buildFileTree, FileTree } from "@/components/FileTree";
import { Card, CardBody, CardHeader, PageHeader } from "@/components/ui";
import {
  api, type BlastRow, type GraphFile, type GraphFiles, type GraphSummary, type Repo, type SymbolDetail, type SymbolRow,
} from "@/lib/api";

type Pane = "code" | "graph" | "ast";

const KIND_COLOR: Record<string, string> = {
  class: "text-amber-400", interface: "text-amber-300", type: "text-amber-200",
  function: "text-sky-400", method: "text-violet-400",
};

function langOf(path: string) {
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "js" || ext === "jsx" || ext === "mjs" || ext === "cjs") return "javascript";
  if (ext === "ts") return "typescript";
  if (ext === "tsx") return "tsx";
  return "python";
}

export default function ExplorerPage() {
  return (
    <Suspense fallback={<Loader2 className="h-6 w-6 animate-spin text-emerald-500" />}>
      <Explorer />
    </Suspense>
  );
}

function Explorer() {
  const router = useRouter();
  const params = useSearchParams();

  const [repos, setRepos] = useState<Repo[]>([]);
  const [repoId, setRepoId] = useState(params.get("repo") ?? "");
  const [pane, setPane] = useState<Pane>((params.get("pane") as Pane) || "code");

  const [graph, setGraph] = useState<GraphFiles | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [focus, setFocus] = useState(true);
  const [summary, setSummary] = useState<GraphSummary | null>(null);
  const [reindexing, setReindexing] = useState(false);

  const [path, setPath] = useState(params.get("path") ?? "");
  const [code, setCode] = useState("");
  const [codeLoading, setCodeLoading] = useState(false);
  const [fileInfo, setFileInfo] = useState<GraphFile | null>(null);
  const [fileErr, setFileErr] = useState<string | null>(null);

  const [symbolId, setSymbolId] = useState<string | null>(params.get("symbol"));
  const [symbol, setSymbol] = useState<SymbolDetail | null>(null);
  const [blast, setBlast] = useState<BlastRow[] | null>(null);
  const [blastLoading, setBlastLoading] = useState(false);

  const [ast, setAst] = useState<any>(null);
  const [astErr, setAstErr] = useState<string | null>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const lineRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SymbolRow[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => { api.repos.list().then(rs => { setRepos(rs); if (!repoId && rs[0]) setRepoId(rs[0].id); }).catch(() => {}); }, []);

  // sync URL
  useEffect(() => {
    const sp = new URLSearchParams();
    if (repoId) sp.set("repo", repoId);
    if (path) sp.set("path", path);
    if (symbolId) sp.set("symbol", symbolId);
    if (pane !== "code") sp.set("pane", pane);
    router.replace(`/explorer?${sp.toString()}`);
  }, [repoId, path, symbolId, pane]);

  useEffect(() => {
    if (!repoId) return;
    setGraphLoading(true); setGraph(null);
    api.graph.files(repoId).then(setGraph).catch(() => setGraph({ nodes: [], edges: [] })).finally(() => setGraphLoading(false));
    api.graph.summary(repoId).then(setSummary).catch(() => setSummary(null));
  }, [repoId]);

  async function reindex() {
    if (!repoId || reindexing) return;
    setReindexing(true);
    try {
      await api.repos.baseline(repoId, true);
      for (let i = 0; i < 300; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const run = await api.repos.latestBaseline(repoId).catch(() => null);
        if (run && run.status !== "running" && run.status !== "queued") break;
      }
      const [g, s] = await Promise.all([api.graph.files(repoId), api.graph.summary(repoId)]);
      setGraph(g); setSummary(s);
      if (path) api.graph.file(repoId, path).then(setFileInfo).catch(() => {});
    } finally { setReindexing(false); }
  }

  useEffect(() => {
    if (!repoId || !path) { setCode(""); setFileInfo(null); return; }
    setCodeLoading(true); setFileErr(null); setAst(null); setSelectedLine(null);
    Promise.all([
      api.repos.getFileContent(repoId, path).then(r => setCode(r.content)).catch(e => setFileErr(String(e))),
      api.graph.file(repoId, path).then(setFileInfo).catch(() => setFileInfo(null)),
    ]).finally(() => setCodeLoading(false));
  }, [repoId, path]);

  useEffect(() => {
    if (!repoId || !symbolId) { setSymbol(null); setBlast(null); return; }
    setBlast(null);
    api.graph.symbol(repoId, symbolId).then(d => {
      setSymbol(d);
      if (d.symbol.path !== path) setPath(d.symbol.path);
      setSelectedLine(d.symbol.start_line);
      setTimeout(() => lineRefs.current[d.symbol.start_line]?.scrollIntoView({ block: "center", behavior: "smooth" }), 50);
    }).catch(() => setSymbol(null));
  }, [repoId, symbolId]);

  useEffect(() => {
    if (pane !== "ast" || !code) return;
    api.admin.parseAst(code, langOf(path)).then(r => { if (r.status === "success") { setAst(r.ast); setAstErr(null); } else setAstErr(r.error ?? "parse failed"); })
      .catch(e => setAstErr(String(e)));
  }, [pane, code, path]);

  useEffect(() => {
    if (!repoId || q.trim().length < 2) { setHits([]); return; }
    const t = setTimeout(() => api.graph.search(repoId, q).then(setHits).catch(() => setHits([])), 180);
    return () => clearTimeout(t);
  }, [q, repoId]);

  const files = useMemo(() => graph?.nodes.map(n => n.path) ?? [], [graph]);
  const tree = useMemo(() => buildFileTree(files), [files]);
  const fanIn = useMemo(() => new Map(graph?.nodes.map(n => [n.path, n.fan_in]) ?? []), [graph]);
  const codeLines = useMemo(() => code.split("\n"), [code]);
  const symbolAtLine = useMemo(() => {
    const m = new Map<number, SymbolRow>();
    for (const s of fileInfo?.symbols ?? []) m.set(s.start_line, s);
    return m;
  }, [fileInfo]);
  const selectedRange = symbol && symbol.symbol.path === path ? [symbol.symbol.start_line, symbol.symbol.end_line] : null;

  function pickLine(n: number) {
    setSelectedLine(n);
    const inner = (fileInfo?.symbols ?? []).filter(s => s.start_line <= n && n <= s.end_line)
      .sort((a, b) => (a.end_line - a.start_line) - (b.end_line - b.start_line))[0];
    if (inner) setSymbolId(inner.id);
  }

  function pickFile(p: string) { setPath(p); setSymbolId(null); setSymbol(null); setBlast(null); }

  async function loadBlast() {
    if (!repoId || !symbolId) return;
    setBlastLoading(true);
    try { setBlast(await api.graph.blast(repoId, symbolId, 2)); } finally { setBlastLoading(false); }
  }

  const repo = repos.find(r => r.id === repoId);

  return (
    <div className="space-y-4">
      <PageHeader title="Code Explorer"
        subtitle="Symbol graph from the latest baseline: definitions, callers, imports, blast radius. Click code to inspect the enclosing symbol."
        actions={
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-3" />
              <input value={q} onChange={e => { setQ(e.target.value); setSearchOpen(true); }} onFocus={() => setSearchOpen(true)}
                onBlur={() => setTimeout(() => setSearchOpen(false), 150)}
                placeholder="Search symbols…" className="w-64 pl-7 pr-7 py-1.5 text-sm font-mono" />
              {q && <button onClick={() => { setQ(""); setHits([]); }} className="absolute right-2 top-1/2 -translate-y-1/2 text-text-3 hover:text-text-1"><X className="h-3.5 w-3.5" /></button>}
              {searchOpen && hits.length > 0 && (
                <div className="absolute right-0 z-40 mt-1 max-h-80 w-[28rem] overflow-y-auto rounded-md border border-border bg-panel shadow-2xl">
                  {hits.map(h => (
                    <button key={h.id} onMouseDown={() => { setSymbolId(h.id); setQ(""); setHits([]); }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-panel-2">
                      <span className={clsx("w-14 shrink-0 text-[10px] uppercase", KIND_COLOR[h.kind] ?? "text-text-3")}>{h.kind}</span>
                      <span className="font-mono text-text-1">{h.name}</span>
                      <span className="ml-auto truncate font-mono text-[10px] text-text-3">{h.path}:{h.start_line}</span>
                      <span className="shrink-0 text-[10px] text-emerald-400">{h.callers} callers</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <select value={repoId} onChange={e => { setRepoId(e.target.value); pickFile(""); }} className="px-3 py-1.5 text-sm">
              {repos.length === 0 && <option value="">No repositories</option>}
              {repos.map(r => <option key={r.id} value={r.id}>{r.full_name}</option>)}
            </select>
          </div>
        } />

      {graph && !graphLoading && (graph.nodes.length === 0 || (summary && summary.references === 0)) && (
        <div className="flex items-center justify-between gap-4 rounded-lg border border-amber-900/50 bg-amber-950/20 px-4 py-3 text-xs text-amber-300">
          <span>
            {graph.nodes.length === 0 ? "This repository has no indexed graph yet."
              : "This index predates cross-file linking — symbols exist but no references or imports."}
            {" "}Re-index to build the dependency graph{summary?.indexed_at ? ` (last indexed ${new Date(summary.indexed_at).toLocaleDateString()})` : ""}.
          </span>
          <button onClick={reindex} disabled={reindexing}
            className="shrink-0 rounded-md bg-amber-600/20 px-3 py-1.5 font-medium text-amber-200 hover:bg-amber-600/30 disabled:opacity-60">
            {reindexing ? <span className="flex items-center gap-1.5"><Loader2 className="h-3 w-3 animate-spin" />Indexing…</span> : "Re-index now"}
          </button>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-12">
        {/* Files */}
        <Card className="flex max-h-[78vh] flex-col lg:col-span-2">
          <CardHeader title="Files" subtitle={graph ? `${graph.nodes.length} indexed` : undefined} />
          <CardBody className="flex-1 overflow-y-auto p-2">
            {graphLoading ? <Loader2 className="mx-auto mt-8 h-5 w-5 animate-spin text-emerald-500" />
              : <FileTree nodes={tree} selected={path} onSelect={pickFile}
                  badge={p => (fanIn.get(p) ?? 0) > 0 ? <span className="ml-auto text-[9px] text-emerald-500/80">{fanIn.get(p)}</span> : null} />}
          </CardBody>
        </Card>

        {/* Main pane */}
        <Card className="flex max-h-[78vh] flex-col lg:col-span-7">
          <div className="flex items-center justify-between border-b border-border px-4 py-2">
            <div className="flex items-center gap-1">
              {([["code", Code2, "Code"], ["graph", Network, "Dependency graph"], ["ast", Braces, "Parse tree"]] as const).map(([k, Icon, label]) => (
                <button key={k} onClick={() => setPane(k)}
                  className={clsx("flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors",
                    pane === k ? "bg-emerald-600/10 text-emerald-400" : "text-text-3 hover:bg-panel-2 hover:text-text-1")}>
                  <Icon className="h-3.5 w-3.5" />{label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3 text-[11px] text-text-3">
              {pane === "graph" && (
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input type="checkbox" checked={focus} onChange={e => setFocus(e.target.checked)} className="h-3 w-3" />
                  neighbourhood only
                </label>
              )}
              {path && <span className="truncate font-mono">{path}</span>}
            </div>
          </div>

          <CardBody className={clsx("flex-1 overflow-auto p-0", pane === "graph" && "min-h-[60vh]")}>
            {pane === "graph" && (graph ? <DependencyGraph data={graph} selected={path || null} onSelect={pickFile} focus={focus} />
              : <Loader2 className="mx-auto mt-16 h-5 w-5 animate-spin text-emerald-500" />)}

            {pane === "code" && (
              !path ? <Empty icon={FileText} title="Pick a file" hint="Choose a file on the left, or search for a symbol above." />
              : codeLoading ? <Loader2 className="mx-auto mt-16 h-5 w-5 animate-spin text-emerald-500" />
              : fileErr ? <div className="p-4 text-xs text-red-300">{fileErr}</div>
              : (
                <div className="flex min-h-full font-mono text-[11px] leading-5">
                  <div className="select-none border-r border-border bg-[#0b0c10] px-2 py-3 text-right text-text-3 tabular-nums">
                    {codeLines.map((_, i) => <div key={i}>{i + 1}</div>)}
                  </div>
                  <div className="flex-1 whitespace-pre py-3">
                    {codeLines.map((line, i) => {
                      const n = i + 1;
                      const sym = symbolAtLine.get(n);
                      const inRange = selectedRange && n >= selectedRange[0] && n <= selectedRange[1];
                      return (
                        <div key={i} ref={el => { lineRefs.current[n] = el; }} onClick={() => pickLine(n)}
                          className={clsx("relative cursor-pointer border-l-2 px-3 hover:bg-panel-2",
                            selectedLine === n ? "border-emerald-500 bg-emerald-950/40 text-emerald-200"
                            : inRange ? "border-emerald-800/60 bg-emerald-950/15" : "border-transparent")}>
                          {sym && (
                            <span className={clsx("absolute -left-[1px] top-0 h-5 w-[3px]", sym.kind === "class" ? "bg-amber-400/70" : "bg-sky-400/70")} title={`${sym.kind} ${sym.name}`} />
                          )}
                          {line || " "}
                          {sym && (sym.callers ?? 0) > 0 && (
                            <span className="ml-3 rounded bg-emerald-950/60 px-1 text-[9px] text-emerald-400">{sym.callers} callers</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )
            )}

            {pane === "ast" && (
              !code ? <Empty icon={Braces} title="Parse tree" hint="Select a file to see its raw AST." />
              : astErr ? <div className="p-4 text-xs text-red-300">{astErr}</div>
              : ast ? <div className="p-3"><AstNode node={ast} selectedLine={selectedLine} onSelect={n => { setSelectedLine(n); lineRefs.current[n]?.scrollIntoView({ block: "center" }); }} /></div>
              : <Loader2 className="mx-auto mt-16 h-5 w-5 animate-spin text-emerald-500" />
            )}
          </CardBody>
        </Card>

        {/* Inspector */}
        <Card className="flex max-h-[78vh] flex-col lg:col-span-3">
          <CardHeader title={symbol ? "Symbol" : "File"} subtitle={symbol ? symbol.symbol.symbol_key : fileInfo?.file.path}
            action={symbol && <button onClick={() => { setSymbolId(null); setSymbol(null); setBlast(null); }} className="text-[11px] text-text-3 hover:text-text-1">← file</button>} />
          <CardBody className="flex-1 space-y-4 overflow-y-auto p-3 text-xs">
            {symbol ? (
              <>
                <div className="rounded-md border border-border bg-[#0b0c10] p-2.5">
                  <div className="flex items-center gap-2">
                    <span className={clsx("text-[10px] uppercase", KIND_COLOR[symbol.symbol.kind] ?? "text-text-3")}>{symbol.symbol.kind}</span>
                    <span className="font-mono text-sm text-text-1">{symbol.symbol.name}</span>
                    <span className="ml-auto text-[10px] text-text-3">{symbol.symbol.visibility}</span>
                  </div>
                  {symbol.symbol.signature && <pre className="mt-2 whitespace-pre-wrap font-mono text-[10.5px] text-text-2">{symbol.symbol.signature}</pre>}
                  {symbol.symbol.docstring && <p className="mt-2 text-[11px] text-text-3">{symbol.symbol.docstring.split("\n")[0]}</p>}
                  <div className="mt-2 font-mono text-[10px] text-text-3">{symbol.symbol.path}:{symbol.symbol.start_line}–{symbol.symbol.end_line}</div>
                </div>

                <Section icon={ArrowDownLeft} title="Callers" count={symbol.callers.length} tone="emerald">
                  {symbol.callers.length === 0 && <Muted>No indexed references.</Muted>}
                  {symbol.callers.map((c, i) => (
                    <RefRowItem key={i} name={c.name ?? "(module level)"} kind={c.kind ?? "file"} path={c.ref_path ?? c.path} line={c.ref_line}
                      tag={c.ref_kind} dim={c.precision === "heuristic"} onClick={() => c.id ? setSymbolId(c.id) : pickFile(c.ref_path ?? c.path)} />
                  ))}
                </Section>

                <Section icon={ArrowUpRight} title="Callees" count={symbol.callees.length} tone="sky">
                  {symbol.callees.length === 0 && <Muted>Calls nothing indexed.</Muted>}
                  {symbol.callees.map((c, i) => (
                    <RefRowItem key={i} name={c.name} kind={c.kind} path={c.path} line={c.start_line} tag={c.ref_kind}
                      dim={c.precision === "heuristic"} onClick={() => setSymbolId(c.id)} />
                  ))}
                </Section>

                <Section icon={Radar} title="Blast radius" count={blast?.length} tone="amber"
                  action={!blast && <button onClick={loadBlast} className="rounded border border-border px-2 py-0.5 text-[10px] text-text-2 hover:bg-panel-2">
                    {blastLoading ? <Loader2 className="inline h-3 w-3 animate-spin" /> : "compute · depth 2"}</button>}>
                  {blast && blast.length === 0 && <Muted>Nothing depends on this symbol.</Muted>}
                  {blast?.map((b, i) => (
                    <RefRowItem key={i} name={b.name} kind={b.kind} path={b.path} line={b.start_line}
                      tag={`d${b.depth} · via ${b.target_name}`} dim={b.precision === "heuristic"} onClick={() => setSymbolId(b.id)} />
                  ))}
                  {blast && blast.length > 0 && (
                    <p className="pt-1 text-[10px] text-text-3">This is the context a PR touching <span className="font-mono">{symbol.symbol.name}</span> gets reviewed with.</p>
                  )}
                </Section>
              </>
            ) : fileInfo ? (
              <>
                <div className="grid grid-cols-3 gap-2">
                  <Stat label="symbols" value={fileInfo.symbols.length} />
                  <Stat label="LOC" value={fileInfo.file.loc} />
                  <Stat label="resolved" value={`${fileInfo.file.resolved_refs}/${fileInfo.file.resolved_refs + fileInfo.file.unresolved_refs}`} />
                </div>

                <Section icon={Crosshair} title="Outline" count={fileInfo.symbols.length}>
                  {fileInfo.symbols.map(s => (
                    <button key={s.id} onClick={() => setSymbolId(s.id)}
                      className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-panel-2">
                      <span className={clsx("w-12 shrink-0 text-[9px] uppercase", KIND_COLOR[s.kind] ?? "text-text-3")}>{s.kind}</span>
                      <span className="truncate font-mono text-text-1">{s.name}</span>
                      <span className="ml-auto shrink-0 text-[10px] tabular-nums text-text-3">L{s.start_line}</span>
                      {(s.callers ?? 0) > 0 && <span className="shrink-0 text-[10px] text-emerald-400">{s.callers}↙</span>}
                    </button>
                  ))}
                </Section>

                <Section icon={ArrowUpRight} title="Imports" count={fileInfo.imports.length} tone="sky">
                  {fileInfo.imports.length === 0 && <Muted>No repo-internal imports.</Muted>}
                  {fileInfo.imports.map((i, k) => <FileRowItem key={k} path={i.path} meta={`L${i.line}`} onClick={() => pickFile(i.path)} />)}
                </Section>

                <Section icon={ArrowDownLeft} title="Imported by" count={fileInfo.importers.length} tone="emerald">
                  {fileInfo.importers.length === 0 && <Muted>Nothing imports this file.</Muted>}
                  {fileInfo.importers.map((i, k) => <FileRowItem key={k} path={i.path} meta={`L${i.line}`} onClick={() => pickFile(i.path)} />)}
                </Section>

                <Section icon={GitFork} title="Reference flow" count={fileInfo.incoming.length + fileInfo.outgoing.length}>
                  {fileInfo.incoming.map((r, k) => <FileRowItem key={`i${k}`} path={r.path} meta={`${r.refs} refs →  here`} onClick={() => pickFile(r.path)} />)}
                  {fileInfo.outgoing.map((r, k) => <FileRowItem key={`o${k}`} path={r.path} meta={`here → ${r.refs} refs`} onClick={() => pickFile(r.path)} />)}
                  {fileInfo.incoming.length + fileInfo.outgoing.length === 0 && <Muted>No cross-file references.</Muted>}
                </Section>
              </>
            ) : path && !codeLoading ? (
              <Muted>This file is not in the index. Re-run the baseline to include it.</Muted>
            ) : (
              <Empty icon={Network} title="Inspector" hint="Select a file or symbol to see its dependencies, callers and blast radius." />
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Section({ icon: Icon, title, count, tone, action, children }: {
  icon: any; title: string; count?: number; tone?: "emerald" | "sky" | "amber"; action?: React.ReactNode; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const color = tone === "emerald" ? "text-emerald-400" : tone === "sky" ? "text-sky-400" : tone === "amber" ? "text-amber-400" : "text-text-2";
  return (
    <div>
      <div className="flex items-center gap-1.5 py-1">
        <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-2">
          {open ? <ChevronDown className="h-3 w-3 text-text-3" /> : <ChevronRight className="h-3 w-3 text-text-3" />}
          <Icon className={clsx("h-3.5 w-3.5", color)} />{title}
          {count !== undefined && <span className="text-text-3">{count}</span>}
        </button>
        <span className="ml-auto">{action}</span>
      </div>
      {open && <div className="space-y-0.5">{children}</div>}
    </div>
  );
}

function RefRowItem({ name, kind, path, line, tag, dim, onClick }: {
  name: string; kind: string; path: string; line: number; tag?: string; dim?: boolean; onClick: () => void;
}) {
  return (
    <button onClick={onClick} className={clsx("flex w-full flex-col rounded px-1.5 py-1 text-left hover:bg-panel-2", dim && "opacity-60")} title={dim ? "heuristic match (name-unique)" : undefined}>
      <span className="flex items-center gap-2">
        <span className={clsx("w-12 shrink-0 text-[9px] uppercase", KIND_COLOR[kind] ?? "text-text-3")}>{kind}</span>
        <span className="truncate font-mono text-text-1">{name}</span>
        {tag && <span className="ml-auto shrink-0 rounded bg-panel-2 px-1 text-[9px] text-text-3">{tag}</span>}
      </span>
      <span className="truncate pl-14 font-mono text-[10px] text-text-3">{path}:{line}</span>
    </button>
  );
}

function FileRowItem({ path, meta, onClick }: { path: string; meta?: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-panel-2">
      <FileText className="h-3 w-3 shrink-0 text-sky-500/70" />
      <span className="truncate font-mono text-text-2">{path}</span>
      {meta && <span className="ml-auto shrink-0 text-[10px] text-text-3">{meta}</span>}
    </button>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-[#0b0c10] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-text-3">{label}</div>
      <div className="font-mono text-sm text-text-1">{value}</div>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="px-1.5 py-1 text-[11px] text-text-3">{children}</p>;
}

function Empty({ icon: Icon, title, hint }: { icon: any; title: string; hint: string }) {
  return (
    <div className="flex h-full min-h-[40vh] flex-col items-center justify-center p-8 text-center text-text-3">
      <Icon className="mb-3 h-8 w-8 opacity-30" />
      <p className="text-sm font-medium text-text-2">{title}</p>
      <p className="mt-1 max-w-xs text-xs">{hint}</p>
    </div>
  );
}

function AstNode({ node, selectedLine, onSelect }: { node: any; selectedLine: number | null; onSelect: (n: number) => void }) {
  const [open, setOpen] = useState(true);
  const kids = node.children?.length ? node.children : null;
  const sel = selectedLine !== null && node.line === selectedLine;
  return (
    <div className="my-0.5 border-l border-border pl-3">
      <div onClick={() => node.line && onSelect(node.line)}
        className={clsx("flex items-center gap-1.5 rounded px-1.5 py-0.5 text-xs", node.line && "cursor-pointer", sel ? "bg-emerald-950/40 text-emerald-300" : "hover:bg-panel-2")}>
        {kids ? <button onClick={e => { e.stopPropagation(); setOpen(!open); }} className="text-text-3">{open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}</button> : <span className="w-3" />}
        <span className="font-mono text-emerald-400">{node.type}</span>
        {node.line && <span className="text-[9px] text-text-3">L{node.line}</span>}
        {node.text && <span className="truncate rounded bg-[#0b0c10] px-1 font-mono text-[10px] text-amber-300">{String(node.text)}</span>}
      </div>
      {kids && open && kids.map((c: any, i: number) => <AstNode key={i} node={c} selectedLine={selectedLine} onSelect={onSelect} />)}
    </div>
  );
}
