"use client";

import clsx from "clsx";
import { ChevronDown, ChevronRight, FileText, Folder } from "lucide-react";
import { useState } from "react";

export type FileNode = { name: string; path: string; isDir: boolean; children: FileNode[] };

export function buildFileTree(files: string[]): FileNode[] {
  const root: FileNode[] = [];
  for (const path of files) {
    const parts = path.split("/");
    let level = root;
    let cur = "";
    parts.forEach((part, i) => {
      cur = cur ? `${cur}/${part}` : part;
      const isDir = i < parts.length - 1;
      let node = level.find(n => n.name === part);
      if (!node) {
        node = { name: part, path: cur, isDir, children: [] };
        level.push(node);
      }
      if (isDir) level = node.children;
    });
  }
  const sort = (nodes: FileNode[]) => {
    nodes.sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1));
    nodes.forEach(n => n.isDir && sort(n.children));
  };
  sort(root);
  return root;
}

export function FileTree({ nodes, selected, onSelect, badge }: {
  nodes: FileNode[]; selected: string; onSelect: (path: string) => void;
  badge?: (path: string) => React.ReactNode;
}) {
  return (
    <div className="space-y-0.5">
      {nodes.map(n => <FileTreeNode key={n.path} node={n} selected={selected} onSelect={onSelect} badge={badge} depth={0} />)}
    </div>
  );
}

function FileTreeNode({ node, selected, onSelect, badge, depth }: {
  node: FileNode; selected: string; onSelect: (p: string) => void; badge?: (p: string) => React.ReactNode; depth: number;
}) {
  const [open, setOpen] = useState(depth < 1 || selected.startsWith(node.path + "/"));
  if (node.isDir) {
    return (
      <div>
        <button onClick={() => setOpen(!open)}
          className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs font-medium text-text-2 hover:bg-panel-2 hover:text-text-1"
          style={{ paddingLeft: 6 + depth * 12 }}>
          {open ? <ChevronDown className="h-3 w-3 text-text-3" /> : <ChevronRight className="h-3 w-3 text-text-3" />}
          <Folder className="h-3.5 w-3.5 shrink-0 text-emerald-500/80" />
          <span className="truncate">{node.name}</span>
        </button>
        {open && node.children.map(c => (
          <FileTreeNode key={c.path} node={c} selected={selected} onSelect={onSelect} badge={badge} depth={depth + 1} />
        ))}
      </div>
    );
  }
  const active = selected === node.path;
  return (
    <button onClick={() => onSelect(node.path)}
      className={clsx("flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left font-mono text-xs transition-colors",
        active ? "bg-emerald-600/10 text-emerald-400" : "text-text-3 hover:bg-panel-2 hover:text-text-2")}
      style={{ paddingLeft: 6 + depth * 12 + 16 }}>
      <FileText className="h-3.5 w-3.5 shrink-0 text-sky-500/80" />
      <span className="truncate">{node.name}</span>
      {badge?.(node.path)}
    </button>
  );
}
