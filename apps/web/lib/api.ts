import { apiBaseUrl } from "@/lib/config";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await r.text();
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
  },
};
