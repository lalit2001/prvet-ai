import { apiBaseUrl } from "@/lib/config";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("crv_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }
  
  const r = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers ?? {}) },
  });
  
  const body = await r.text();
  
  if (r.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("crv_token");
    localStorage.removeItem("crv_role");
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
  
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${body.slice(0, 500)}`);
  return body ? (JSON.parse(body) as T) : ({} as T);
}

export type Repo = {
  id: string; full_name: string; clone_url: string;
  default_branch: string; is_enabled: boolean;
};

export type Finding = {
  id: string; source: string; category: string; severity: string;
  title: string; body: string; file_path: string;
  start_line: number | null; end_line: number | null;
  confidence: number; status: string; created_at: string;
  suggested_patch?: string | null;
  resolution?: any;
};

export type ReviewResult = {
  summary: string;
  findings: Array<{
    category: string; severity: string; confidence: number;
    title: string; body: string;
    start_line: number | null; end_line: number | null;
    suggested_patch: string | null;
  }>;
  error: string | null;
  stats: Record<string, unknown>;
};

export type OrgConfig = {
  llm: { base_url: string; api_key_ref: string; model_fast: string; model_deep: string; monthly_budget_usd: number; };
  gate: {
    mode: "fail_open" | "fail_closed";
    block_severity: "critical" | "high" | "medium" | "low" | "info";
    min_confidence: number;
    max_comments_per_pr: number;
  };
  custom_rules: CustomRule[];
};

export type CustomRule = {
  id: string; language: string; severity: string; category: string;
  message: string; pattern: string; pattern_not?: string; fix?: string; enabled?: boolean;
};

export type RepoConfig = {
  review: { block_severity: string; categories: string[]; min_confidence: number; drafts: boolean; guidelines: string; };
  bypass: { roles: string[]; require_second_approver_for: string[] };
  exclude_paths: string[];
  hotspots: { count: number; extra: string[] };
  weekly: { schedule: string; auto_promote_baseline: boolean };
};

export type Run = {
  id: string; repo_id: string; repo: string;
  run_type: string; status: string; commit_sha: string;
  duration_ms: number | null; stats: Record<string, unknown>;
  created_at: string; finished_at: string | null;
};

export type RunDetail = {
  id: string;
  run_type: string;
  status: string;
  commit_sha: string;
  duration_ms: number | null;
  stats: {
    phase?: "indexing" | "reviewing" | "summarizing" | "done";
    files_seen?: number;
    files_indexed?: number;
    files_skipped?: number;
    symbols?: number;
    by_language?: Record<string, number>;
    hotspots_total?: number;
    hotspots_done?: number;
    findings?: number;
    cost_usd?: number;
    summary?: string;
  };
  created_at: string;
  finished_at: string | null;
  findings_count: number;
};

export type ProviderType =
  | "openai" | "anthropic" | "azure_openai" | "azure_ai" | "bedrock"
  | "vertex_ai" | "ollama" | "vllm" | "litellm" | "openai_compatible";

export type Provider = {
  id: string;
  type: ProviderType;
  name: string;
  enabled: boolean;
  api_key?: string | null;
  endpoint?: string | null;
  api_version?: string | null;
  region?: string | null;
  access_key_id?: string | null;
  secret_access_key?: string | null;
  project?: string | null;
  location?: string | null;
  credentials_json?: string | null;
  base_url?: string | null;
  role_map: Record<string, string>;
};

export type GraphSummary = {
  files: number; symbols: number; references: number; file_imports: number;
  resolved: number; unresolved: number; resolution_rate: number | null; indexed_at: string | null;
  by_language: Array<{ language: string; files: number; loc: number }>;
  symbol_kinds: Array<{ kind: string; n: number }>;
  top_files: Array<{ path: string; language: string; loc: number; fan_in: number }>;
  top_symbols: Array<{ id: string; symbol_key: string; name: string; kind: string; path: string; start_line: number; callers: number }>;
};
export type GraphFileNode = { id: string; path: string; language: string; loc: number; symbols: number; fan_in: number; fan_out: number };
export type GraphFiles = { nodes: GraphFileNode[]; edges: Array<{ source: string; target: string; weight: number }> };
export type SymbolRow = {
  id: string; symbol_key: string; name: string; kind: string; visibility?: string; signature?: string | null;
  docstring?: string | null; start_line: number; end_line: number; path: string; callers?: number; callees?: number;
};
export type GraphFile = {
  file: { id: string; path: string; language: string; loc: number; indexed_at_sha: string; resolved_refs: number; unresolved_refs: number; updated_at: string };
  symbols: SymbolRow[];
  imports: Array<{ path: string; file_id: string; line: number; specifier: string }>;
  importers: Array<{ path: string; file_id: string; line: number; specifier: string }>;
  outgoing: Array<{ path: string; refs: number }>;
  incoming: Array<{ path: string; refs: number }>;
};
export type RefRow = SymbolRow & { ref_line: number; ref_kind: string; precision: string; ref_path?: string };
export type SymbolDetail = { symbol: SymbolRow; callers: RefRow[]; callees: RefRow[] };
export type BlastRow = SymbolRow & { target_id: string; target_name: string; target_key: string; ref_line: number; ref_kind: string; precision: string; depth: number; score: number };

export const api = {
  health: () => req<{ status: string }>("/healthz"),
  ready: () => req<Record<string, { status: string; error?: string }>>("/readyz"),

  repos: {
    list: () => req<Repo[]>("/api/v1/repos"),
    createLocal: (name: string, local_path: string) =>
      req<Repo>("/api/v1/repos/local", { method: "POST", body: JSON.stringify({ name, local_path }) }),
    baseline: (id: string, force = false) =>
      req<{ run_id: string; status: string; cached: boolean }>(
        `/api/v1/repos/${id}/baseline${force ? "?force=true" : ""}`, { method: "POST" }),
    latestBaseline: (id: string) => req<RunDetail | null>(`/api/v1/repos/${id}/latest-baseline`),
    findings: (id: string) => req<Finding[]>(`/api/v1/repos/${id}/findings`),
    getConfig: (id: string) => req<RepoConfig>(`/api/v1/repos/${id}/config`),
    putConfig: (id: string, cfg: RepoConfig) =>
      req<RepoConfig>(`/api/v1/repos/${id}/config`, { method: "PUT", body: JSON.stringify(cfg) }),
    remove: (id: string) => req<void>(`/api/v1/repos/${id}`, { method: "DELETE" }),
    getFiles: (id: string) => req<string[]>(`/api/v1/repos/${id}/files`),
    getFileContent: (id: string, path: string) =>
      req<{ content: string }>(`/api/v1/repos/${id}/file-content?path=${encodeURIComponent(path)}`),
  },

  graph: {
    summary: (repoId: string) => req<GraphSummary>(`/api/v1/repos/${repoId}/graph/summary`),
    files: (repoId: string) => req<GraphFiles>(`/api/v1/repos/${repoId}/graph/files`),
    file: (repoId: string, path: string) => req<GraphFile>(`/api/v1/repos/${repoId}/graph/file?path=${encodeURIComponent(path)}`),
    search: (repoId: string, q: string) => req<SymbolRow[]>(`/api/v1/repos/${repoId}/symbols/search?q=${encodeURIComponent(q)}`),
    symbol: (repoId: string, id: string) => req<SymbolDetail>(`/api/v1/repos/${repoId}/symbols/${id}`),
    blast: (repoId: string, id: string, depth = 2) => req<BlastRow[]>(`/api/v1/repos/${repoId}/symbols/${id}/blast?depth=${depth}`),
  },

  reviews: {
    adhoc: (code: string, language?: string, repo_id?: string) =>
      req<ReviewResult>("/api/v1/reviews/adhoc", {
        method: "POST",
        body: JSON.stringify({ code, language, repo_id }),
      }),
  },

  config: {
    getOrg: () => req<OrgConfig>("/api/v1/config/org"),
    putOrg: (cfg: OrgConfig) => req<OrgConfig>("/api/v1/config/org", { method: "PUT", body: JSON.stringify(cfg) }),
    getEnv: () => req<Record<string, string | number>>("/api/v1/config/env"),
  },

  providers: {
    list: () => req<Provider[]>("/api/v1/config/providers"),
    add: (p: Provider) => req<Provider>("/api/v1/config/providers", { method: "POST", body: JSON.stringify(p) }),
    save: (list: Provider[]) => req<Provider[]>("/api/v1/config/providers", { method: "PUT", body: JSON.stringify(list) }),
    remove: (id: string) => req<void>(`/api/v1/config/providers/${id}`, { method: "DELETE" }),
    test: (id: string) => req<{ ok: boolean; provider_id: string; latency_ms: number | null; error: string | null }>(
      `/api/v1/admin/providers/${id}/test`, { method: "POST" }
    ),
  },

  admin: {
    llmTest: () => req<{ ok: boolean; model: string; latency_ms: number | null; error: string | null }>(
      "/api/v1/admin/llm/test", { method: "POST" }
    ),
    runs: () => req<Run[]>("/api/v1/runs"),
    audit: () => req<Array<Record<string, unknown>>>("/api/v1/audit"),
    run: (run_id: string) => req<RunDetail>(`/api/v1/runs/${run_id}`),
    generateRule: (description: string, language: string) =>
      req<Partial<CustomRule>>("/api/v1/admin/rules/generate", {
        method: "POST",
        body: JSON.stringify({ description, language }),
      }),
    parseAst: (code: string, language: string) =>
      req<{ status: string; ast?: any; error?: string }>("/api/v1/admin/ast/parse", {
        method: "POST",
        body: JSON.stringify({ code, language }),
      }),
    users: {
      list: () => req<Array<{ id: string; email: string; display_name: string | null; role: string; is_active: boolean; permitted_repos: string[] }>>("/api/v1/admin/users"),
      create: (body: any) => req<any>("/api/v1/admin/users", { method: "POST", body: JSON.stringify(body) }),
      update: (id: string, body: any) => req<any>(`/api/v1/admin/users/${id}`, { method: "PUT", body: JSON.stringify(body) }),
      delete: (id: string) => req<void>(`/api/v1/admin/users/${id}`, { method: "DELETE" }),
    },
  },

  findings: {
    get: (id: string) => req<Finding & { repo_name: string; repo_id: string; suggested_patch: string | null; resolution: any }>(`/api/v1/findings/${id}`),
    resolve: (id: string, resolution?: any) => req<{ status: string; finding_id: string }>(`/api/v1/findings/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ resolution }),
    }),
  },

  prs: {
    list: () => req<Array<{
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
    }>>("/api/v1/prs"),
  },

  auth: {
    login: (body: any) => req<{ token: string; role: string; email: string; display_name?: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    }),
    me: () => req<{ id: string; email: string; role: string; display_name: string }>("/api/v1/auth/me"),
  },
};
