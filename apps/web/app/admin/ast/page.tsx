"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import clsx from "clsx";
import {
  Code2, Play, Network, ChevronDown, ChevronRight, Loader2,
  FileText, Folder, Database, Info, Sparkles
} from "lucide-react";
import { api, type Repo } from "@/lib/api";
import { Card, CardBody, CardHeader, PageHeader } from "@/components/ui";

const LANGS = ["python", "typescript", "javascript", "tsx"];
const SAMPLE_PYTHON = `def greet(name):
    print("Hello, " + name)
    if not name:
        return None
    return True
`;

type FileNode = {
  name: string;
  path: string;
  isDir: boolean;
  children: FileNode[];
};

function buildFileTree(files: string[]): FileNode[] {
  const root: FileNode[] = [];
  
  for (const path of files) {
    const parts = path.split("/");
    let currentLevel = root;
    let currentPath = "";
    
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isDir = i < parts.length - 1;
      
      let existingNode = currentLevel.find(n => n.name === part);
      if (!existingNode) {
        existingNode = {
          name: part,
          path: currentPath,
          isDir,
          children: []
        };
        currentLevel.push(existingNode);
      }
      
      if (isDir) {
        currentLevel = existingNode.children;
      }
    }
  }
  
  const sortTree = (nodes: FileNode[]) => {
    nodes.sort((a, b) => {
      if (a.isDir && !b.isDir) return -1;
      if (!a.isDir && b.isDir) return 1;
      return a.name.localeCompare(b.name);
    });
    for (const node of nodes) {
      if (node.isDir) sortTree(node.children);
    }
  };
  
  sortTree(root);
  return root;
}

function FileExplorerNode({
  node,
  selectedFile,
  onSelectFile
}: {
  node: FileNode;
  selectedFile: string;
  onSelectFile: (path: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const isDir = node.isDir;
  
  if (isDir) {
    return (
      <div className="pl-2">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 py-1 text-xs text-text-2 hover:text-text-1 w-full text-left font-medium select-none focus:outline-none"
        >
          {open ? <ChevronDown className="h-3 w-3 text-neutral-500" /> : <ChevronRight className="h-3 w-3 text-neutral-500" />}
          <Folder className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
          <span className="truncate">{node.name}</span>
        </button>
        {open && (
          <div className="border-l border-neutral-800 ml-1.5 pl-1.5">
            {node.children.map((c, i) => (
              <FileExplorerNode
                key={i}
                node={c}
                selectedFile={selectedFile}
                onSelectFile={onSelectFile}
              />
            ))}
          </div>
        )}
      </div>
    );
  } else {
    const active = selectedFile === node.path;
    return (
      <div className="pl-2">
        <button
          onClick={() => onSelectFile(node.path)}
          className={clsx(
            "flex items-center gap-1.5 py-1 px-1.5 rounded text-xs w-full text-left font-mono select-none transition-colors focus:outline-none",
            active ? "bg-emerald-950/40 text-emerald-400 font-semibold" : "text-text-3 hover:bg-panel-2 hover:text-text-2"
          )}
        >
          <FileText className="h-3.5 w-3.5 text-blue-500 shrink-0" />
          <span className="truncate">{node.name}</span>
        </button>
      </div>
    );
  }
}

function TreeNode({
  node,
  selectedLine,
  onSelectLine
}: {
  node: any;
  selectedLine: number | null;
  onSelectLine: (line: number) => void;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = selectedLine !== null && node.line === selectedLine;

  const nodeText = node.text ? String(node.text) : "";
  const isLiteral = node.type === "literal" || node.type === "string" || node.type === "number";

  return (
    <div className="pl-4 border-l border-neutral-800 my-1 select-none">
      <div
        onClick={() => node.line && onSelectLine(node.line)}
        className={clsx(
          "flex items-center gap-1.5 py-0.5 text-xs rounded px-1.5 cursor-pointer transition-colors",
          isSelected ? "bg-emerald-500/10 border-l border-emerald-500 font-bold" : "hover:bg-neutral-900/40"
        )}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setOpen(!open);
            }}
            className="p-0.5 text-neutral-500 hover:text-neutral-300 focus:outline-none transition-colors"
          >
            {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        ) : (
          <span className="w-4" />
        )}

        <span className="font-mono text-emerald-400 font-semibold">{node.type}</span>

        {node.line && (
          <span className="text-[9px] text-neutral-500 font-mono">
            (line {node.line})
          </span>
        )}

        {nodeText && (
          <span className={clsx(
            "text-[10px] rounded px-1.5 py-0.5 font-mono border border-neutral-800/40 truncate max-w-[200px]",
            isLiteral ? "text-amber-400 bg-neutral-900" : "text-neutral-300 bg-panel-2 italic"
          )}>
            {nodeText}
          </span>
        )}
      </div>

      {hasChildren && open && (
        <div className="mt-0.5">
          {node.children.map((c: any, i: number) => (
            <TreeNode
              key={i}
              node={c}
              selectedLine={selectedLine}
              onSelectLine={onSelectLine}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function AstViewerPage() {
  const [code, setCode] = useState(SAMPLE_PYTHON);
  const [language, setLanguage] = useState("python");
  const [ast, setAst] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Repositories & Files Explorer
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<string>("");
  const [files, setFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [filesLoading, setFilesLoading] = useState(false);
  const [fileContentLoading, setFileContentLoading] = useState(false);

  // Dual pane interactive highlighting
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const codeLinesRef = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    api.repos.list()
      .then(setRepos)
      .catch(err => console.error("Failed to list repos:", err));
  }, []);

  useEffect(() => {
    if (!selectedRepoId) {
      setFiles([]);
      setSelectedFile("");
      return;
    }
    setFilesLoading(true);
    setFiles([]);
    setSelectedFile("");
    api.repos.getFiles(selectedRepoId)
      .then(setFiles)
      .catch(err => {
        console.error("Failed to fetch repo files:", err);
        setFiles([]);
      })
      .finally(() => setFilesLoading(false));
  }, [selectedRepoId]);

  useEffect(() => {
    if (!selectedRepoId || !selectedFile) return;
    setFileContentLoading(true);
    api.repos.getFileContent(selectedRepoId, selectedFile)
      .then(res => {
        setCode(res.content);
        const ext = selectedFile.split(".").pop()?.toLowerCase();
        let lang = "python";
        if (ext === "js" || ext === "jsx") lang = "javascript";
        else if (ext === "ts") lang = "typescript";
        else if (ext === "tsx") lang = "tsx";
        
        setLanguage(lang);
        setError(null);
        setSelectedLine(null);
      })
      .catch(err => {
        console.error("Failed to load file content:", err);
        setError(`Failed to load file content: ${err}`);
      })
      .finally(() => setFileContentLoading(false));
  }, [selectedRepoId, selectedFile]);

  async function handleParse() {
    if (!code.trim()) return;
    setLoading(true);
    setError(null);
    setAst(null);
    try {
      const res = await api.admin.parseAst(code, language);
      if (res.status === "success" && res.ast) {
        setAst(res.ast);
      } else {
        setError(res.error || "Failed to parse code.");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // Trigger auto parse when code changes (either custom or loaded from file)
  useEffect(() => {
    if (code !== SAMPLE_PYTHON || selectedFile) {
      handleParse();
    }
  }, [code, language]);

  const fileTree = useMemo(() => {
    return buildFileTree(files);
  }, [files]);

  const codeLines = useMemo(() => {
    return code.split("\n");
  }, [code]);

  // Handle bidirectional navigation & highlights
  const handleSelectLine = (lineNum: number) => {
    setSelectedLine(lineNum);
    // Scroll code view to center on selected line
    const el = codeLinesRef.current[lineNum];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="AST Workspace"
        subtitle="Explore code structures side-by-side with parser nodes. Click lines to match AST structures, and vice-versa."
      />

      <div className="grid gap-6 lg:grid-cols-4 items-start">
        {/* Column 1: File Manager Sidebar */}
        <div className="lg:col-span-1 space-y-4">
          <Card className="max-h-[80vh] flex flex-col">
            <CardHeader
              title="File Explorer"
              action={
                <select
                  value={selectedRepoId}
                  onChange={e => setSelectedRepoId(e.target.value)}
                  className="px-2 py-1 text-[10px] bg-panel-2 border border-border text-text-2 rounded focus:outline-none uppercase tracking-wider font-semibold max-w-[120px]"
                >
                  <option value="">Sandbox</option>
                  {repos.map(r => (
                    <option key={r.id} value={r.id}>{r.full_name.split("/").pop()}</option>
                  ))}
                </select>
              }
            />
            <CardBody className="overflow-y-auto flex-1 min-h-[50vh] p-2">
              {!selectedRepoId ? (
                <div className="text-center p-8 text-neutral-500 space-y-2 mt-8">
                  <Sparkles className="h-6 w-6 text-emerald-400/40 mx-auto" />
                  <p className="text-xs">Sandbox Playground</p>
                  <p className="text-[10px] text-neutral-600">Select a project in the dropdown to load Git files here.</p>
                </div>
              ) : filesLoading ? (
                <div className="text-center p-8 text-neutral-500">
                  <Loader2 className="h-6 w-6 animate-spin text-emerald-500 mx-auto" />
                  <p className="text-[10px] mt-2">Loading workspace...</p>
                </div>
              ) : files.length === 0 ? (
                <p className="text-xs text-neutral-600 text-center p-8">No supported files found.</p>
              ) : (
                <div className="space-y-1">
                  {fileTree.map((node, i) => (
                    <FileExplorerNode
                      key={i}
                      node={node}
                      selectedFile={selectedFile}
                      onSelectFile={setSelectedFile}
                    />
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        {/* Columns 2-4: Dual Pane Code vs AST */}
        <div className="lg:col-span-3 grid gap-6 md:grid-cols-2">
          {/* Left: Code Viewer */}
          <Card className="max-h-[80vh] flex flex-col">
            <CardHeader
              title="Source Code"
              subtitle={selectedFile ? selectedFile : "Sandbox Editor"}
              action={
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-text-3 font-semibold">Parser:</span>
                  <select
                    value={language}
                    onChange={e => {
                      setLanguage(e.target.value);
                      if (!selectedFile) {
                        if (e.target.value === "python") setCode(SAMPLE_PYTHON);
                        else setCode(`function greet(name) {\n  console.log("Hello " + name);\n}`);
                      }
                    }}
                    className="px-2 py-1 text-[10px] bg-[#0b0c10] border border-neutral-800 text-neutral-300 rounded focus:outline-none capitalize font-mono"
                  >
                    {LANGS.map(l => (
                      <option key={l}>{l}</option>
                    ))}
                  </select>
                </div>
              }
            />
            <CardBody className="p-0 overflow-y-auto flex-1 bg-neutral-950 font-mono text-xs text-neutral-300 flex">
              {fileContentLoading ? (
                <div className="flex-1 flex flex-col items-center justify-center p-12 text-neutral-500">
                  <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
                  <span className="text-xs mt-2">Loading source code...</span>
                </div>
              ) : (
                <div className="flex-1 flex overflow-x-auto min-h-[55vh]">
                  {/* Line Numbers Gutter */}
                  <div className="bg-[#0b0c10] text-neutral-600 px-3 py-4 text-right select-none border-r border-neutral-900 font-mono text-[11px] leading-5 tabular-nums">
                    {codeLines.map((_, i) => (
                      <div key={i}>{i + 1}</div>
                    ))}
                  </div>
                  {/* Code Line Elements */}
                  <div className="flex-1 py-4 leading-5 font-mono text-[11px] whitespace-pre min-w-[300px]">
                    {codeLines.map((line, idx) => {
                      const lineNum = idx + 1;
                      const isHighlighted = selectedLine === lineNum;
                      return (
                        <div
                          key={idx}
                          ref={el => { codeLinesRef.current[lineNum] = el; }}
                          onClick={(e) => handleSelectLine(lineNum)}
                          className={clsx(
                            "px-4 cursor-pointer hover:bg-neutral-900 transition-colors border-l-2",
                            isHighlighted
                              ? "bg-emerald-950/30 text-emerald-300 border-emerald-500 font-semibold"
                              : "border-transparent"
                          )}
                        >
                          {line || " "}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>

          {/* Right: AST Viewer Tree */}
          <Card className="max-h-[80vh] flex flex-col">
            <CardHeader
              title="Abstract Syntax Tree"
              subtitle="Collapsible AST layout mapping"
              action={
                <div className="flex items-center gap-1 text-[10px] text-neutral-500 uppercase tracking-wider font-mono">
                  <Network className="h-3.5 w-3.5" /> Tree
                </div>
              }
            />
            <CardBody className="overflow-y-auto flex-1 p-4 bg-[#07080b]">
              {error && (
                <div className="rounded-lg border border-red-900 bg-red-950/20 p-4 text-xs text-red-300">
                  <h4 className="font-bold flex items-center gap-1.5 mb-1 text-red-400">Parsing Error</h4>
                  <pre className="whitespace-pre-wrap font-mono mt-1 opacity-90">{error}</pre>
                </div>
              )}

              {loading ? (
                <div className="flex flex-col items-center justify-center p-12 text-neutral-500 min-h-[45vh]">
                  <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
                  <span className="text-xs mt-2">Compiling parser nodes...</span>
                </div>
              ) : ast ? (
                <div className="overflow-x-auto min-h-[45vh]">
                  <TreeNode
                    node={ast}
                    selectedLine={selectedLine}
                    onSelectLine={handleSelectLine}
                  />
                </div>
              ) : (
                !error && (
                  <div className="flex flex-col items-center justify-center p-12 text-center text-neutral-500 min-h-[45vh] border border-dashed border-neutral-800 rounded-xl">
                    <Code2 className="h-10 w-10 opacity-30 animate-pulse mb-3" />
                    <p className="text-sm font-semibold">AST Map</p>
                    <p className="text-xs max-w-xs mt-1 text-neutral-600">
                      View parsed nodes here. Click lines in the code view to highlight their corresponding AST nodes.
                    </p>
                  </div>
                )
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
