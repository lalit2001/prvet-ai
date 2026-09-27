"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphFiles } from "@/lib/api";

const LANG_COLOR: Record<string, string> = {
  python: "#60a5fa", typescript: "#2dd4bf", tsx: "#34d399", javascript: "#facc15",
};

type P = { id: string; x: number; y: number; vx: number; vy: number; r: number };

// ponytail: hand-rolled force layout, O(n²) per tick. Fine to ~400 nodes; swap for d3-force if a repo exceeds that.
function layout(ids: string[], radius: Map<string, number>, edges: Array<[string, string]>, w: number, h: number): Map<string, P> {
  const pts = new Map<string, P>();
  ids.forEach((id, i) => {
    const a = (i / ids.length) * Math.PI * 2;
    const d = Math.min(w, h) * 0.35;
    pts.set(id, { id, x: w / 2 + Math.cos(a) * d, y: h / 2 + Math.sin(a) * d, vx: 0, vy: 0, r: radius.get(id) ?? 4 });
  });
  const arr = [...pts.values()];
  const links = edges.map(([s, t]) => [pts.get(s), pts.get(t)] as [P | undefined, P | undefined]).filter(([a, b]) => a && b) as [P, P][];
  const iters = arr.length > 250 ? 120 : 220;
  for (let k = 0; k < iters; k++) {
    const t = 1 - k / iters;
    for (let i = 0; i < arr.length; i++) {
      const a = arr[i];
      for (let j = i + 1; j < arr.length; j++) {
        const b = arr[j];
        let dx = a.x - b.x, dy = a.y - b.y;
        let d2 = dx * dx + dy * dy || 0.01;
        const min = (a.r + b.r + 6);
        const f = Math.min(1200 / d2, 8) + (d2 < min * min ? 2 : 0);
        const d = Math.sqrt(d2);
        dx /= d; dy /= d;
        a.vx += dx * f * t; a.vy += dy * f * t;
        b.vx -= dx * f * t; b.vy -= dy * f * t;
      }
      // gravity to centre
      a.vx += (w / 2 - a.x) * 0.012 * t;
      a.vy += (h / 2 - a.y) * 0.012 * t;
    }
    for (const [a, b] of links) {
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const want = 60 + a.r + b.r;
      const f = (d - want) * 0.03 * t;
      a.vx += (dx / d) * f; a.vy += (dy / d) * f;
      b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
    }
    for (const p of arr) {
      p.x = Math.max(p.r, Math.min(w - p.r, p.x + p.vx));
      p.y = Math.max(p.r, Math.min(h - p.r, p.y + p.vy));
      p.vx *= 0.6; p.vy *= 0.6;
    }
  }
  return pts;
}

export function DependencyGraph({ data, selected, onSelect, focus }: {
  data: GraphFiles; selected: string | null; onSelect: (path: string) => void; focus: boolean;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 900, h: 560 });
  const [hover, setHover] = useState<string | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: Math.max(420, el.clientHeight) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const byPath = useMemo(() => new Map(data.nodes.map(n => [n.path, n])), [data]);
  const byId = useMemo(() => new Map(data.nodes.map(n => [n.id, n])), [data]);
  const selId = selected ? byPath.get(selected)?.id ?? null : null;

  const neighbours = useMemo(() => {
    const s = new Set<string>();
    if (!selId) return s;
    s.add(selId);
    for (const e of data.edges) {
      if (e.source === selId) s.add(e.target);
      if (e.target === selId) s.add(e.source);
    }
    return s;
  }, [data, selId]);

  const visible = useMemo(() => {
    const showAll = !focus || !selId;
    const nodes = data.nodes.filter(n => showAll || neighbours.has(n.id));
    const ids = new Set(nodes.map(n => n.id));
    const edges = data.edges.filter(e => ids.has(e.source) && ids.has(e.target));
    return { nodes, edges };
  }, [data, focus, selId, neighbours]);

  const pos = useMemo(() => {
    const radius = new Map(visible.nodes.map(n => [n.id, 4 + Math.min(14, Math.sqrt(n.fan_in) * 3)]));
    return layout(visible.nodes.map(n => n.id), radius, visible.edges.map(e => [e.source, e.target]), size.w, size.h);
  }, [visible, size.w, size.h]);

  useEffect(() => setView({ x: 0, y: 0, k: 1 }), [visible.nodes.length]);

  const active = hover ?? selId;
  const activeSet = useMemo(() => {
    const s = new Set<string>();
    if (!active) return s;
    s.add(active);
    for (const e of visible.edges) {
      if (e.source === active) s.add(e.target);
      if (e.target === active) s.add(e.source);
    }
    return s;
  }, [active, visible.edges]);

  const hoverNode = hover ? byId.get(hover) : null;

  return (
    <div ref={wrap} className="relative h-full min-h-[420px] w-full overflow-hidden rounded-lg bg-[#07080b]"
      onWheel={e => {
        e.preventDefault();
        const k = Math.max(0.4, Math.min(4, view.k * (e.deltaY < 0 ? 1.1 : 0.9)));
        setView(v => ({ ...v, k }));
      }}
      onMouseDown={e => { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; }}
      onMouseMove={e => {
        const d = drag.current;
        if (!d) return;
        const x = d.vx + (e.clientX - d.x), y = d.vy + (e.clientY - d.y);
        setView(v => ({ ...v, x, y }));
      }}
      onMouseUp={() => { drag.current = null; }}
      onMouseLeave={() => { drag.current = null; }}>
      <svg width={size.w} height={size.h} className="cursor-grab select-none active:cursor-grabbing">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill="#3f4650" />
          </marker>
          <marker id="arrow-hi" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill="#34d399" />
          </marker>
        </defs>
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {visible.edges.map(e => {
            const a = pos.get(e.source), b = pos.get(e.target);
            if (!a || !b) return null;
            const hi = active && (e.source === active || e.target === active);
            const dim = active && !hi;
            const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
            const ex = b.x - (dx / d) * (b.r + 2), ey = b.y - (dy / d) * (b.r + 2);
            return (
              <line key={`${e.source}-${e.target}`} x1={a.x} y1={a.y} x2={ex} y2={ey}
                stroke={hi ? "#34d399" : "#2a3038"} strokeOpacity={dim ? 0.15 : hi ? 0.9 : 0.6}
                strokeWidth={hi ? 1.6 : Math.min(2.5, 0.6 + e.weight * 0.3)}
                markerEnd={hi ? "url(#arrow-hi)" : "url(#arrow)"} />
            );
          })}
          {visible.nodes.map(n => {
            const p = pos.get(n.id);
            if (!p) return null;
            const isSel = n.id === selId;
            const hi = activeSet.has(n.id);
            const dim = active && !hi;
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.25 : 1}
                onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                onClick={e => { e.stopPropagation(); onSelect(n.path); }} className="cursor-pointer">
                <circle r={p.r} fill={LANG_COLOR[n.language] ?? "#94a3b8"} fillOpacity={isSel ? 1 : 0.75}
                  stroke={isSel ? "#fff" : hi ? "#34d399" : "#0b0c10"} strokeWidth={isSel ? 2 : 1.2} />
                {(hi || p.r > 9 || visible.nodes.length <= 40) && (
                  <text y={p.r + 10} textAnchor="middle" fontSize={9} fill={isSel ? "#e5e7eb" : "#9aa3ad"} className="font-mono pointer-events-none">
                    {n.path.split("/").pop()}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {hoverNode && (
        <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-border bg-panel/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
          <div className="font-mono text-text-1">{hoverNode.path}</div>
          <div className="mt-1 flex gap-3 text-[11px] text-text-3">
            <span>{hoverNode.symbols} symbols</span><span>{hoverNode.loc} LOC</span>
            <span className="text-emerald-400">← {hoverNode.fan_in} importers</span>
            <span className="text-sky-400">→ {hoverNode.fan_out} imports</span>
          </div>
        </div>
      )}

      <div className="absolute bottom-3 left-3 flex flex-wrap items-center gap-3 text-[10px] text-text-3">
        {Object.entries(LANG_COLOR).map(([l, c]) => (
          <span key={l} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: c }} />{l}</span>
        ))}
        <span className={clsx("ml-2", "text-text-3")}>size = importers · arrow = imports · scroll to zoom · drag to pan</span>
      </div>
      <div className="absolute bottom-3 right-3 text-[10px] text-text-3">
        {visible.nodes.length} files · {visible.edges.length} edges{focus && selId ? " · neighbourhood" : ""}
      </div>
    </div>
  );
}
