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
  id: string;
  full_name: string;
  clone_url: string;
  default_branch: string;
  is_enabled: boolean;
};

export type Finding = {
  id: string;
  source: string;
  category: string;
  severity: string;
  title: string;
  body: string;
  file_path: string;
  start_line: number | null;
  end_line: number | null;
  confidence: number;
  status: string;
  created_at: string;
};

export type ReviewResult = {
  summary: string;
  findings: Array<{
    category: string;
    severity: string;
    confidence: number;
    title: string;
    body: string;
    start_line: number | null;
    end_line: number | null;
    suggested_patch: string | null;
  }>;
  error: string | null;
  stats: Record<string, unknown>;
};

export type OrgConfig = {
  llm: {
    base_url: string;
    api_key_ref: string;
    model_fast: string;
    model_deep: string;
    monthly_budget_usd: number;
  };
  gate: {
    mode: "fail_open" | "fail_closed";
    block_severity: "critical" | "high" | "medium" | "low" | "info";
    min_confidence: number;
    max_comments_per_pr: number;
  };
  custom_rules: CustomRule[];
};

export type CustomRule = {
  id: string;
  language: string;
  severity: string;
  category: string;
  message: string;
  pattern: string;
  pattern_not?: string;
  fix?: string;
  enabled?: boolean;
};

export type RepoConfig = {
  review: {
    block_severity: string;
    categories: string[];
    min_confidence: number;
    drafts: boolean;
    guidelines: string;
  };
  bypass: { roles: string[]; require_second_approver_for: string[] };
  exclude_paths: string[];
  hotspots: { count: number; extra: string[] };
  weekly: { schedule: string; auto_promote_baseline: boolean };
};

export type Run = {
  id: string;
  repo_id: string;
  repo: string;
  run_type: string;
  status: string;
  commit_sha: string;
  duration_ms: number | null;
  stats: Record<string, unknown>;
  created_at: string;
  finished_at: string | null;
};

export const api = {
  health: () => req<{ status: string }>("/healthz"),
  ready: () => req<Record<string, { status: string; error?: string }>>("/readyz"),

  repos: {
    list: () => req<Repo[]>("/api/v1/repos"),
    createLocal: (name: string, local_path: string) =>
      req<Repo>("/api/v1/repos/local", { method: "POST", body: JSON.stringify({ name, local_path }) }),
    baseline: (id: string) =>
      req<{ run_id: string; baseline_id: string; files_indexed: number; symbols: number }>(
        `/api/v1/repos/${id}/baseline`, { method: "POST" }
      ),
    findings: (id: string) => req<Finding[]>(`/api/v1/repos/${id}/findings`),
    getConfig: (id: string) => req<RepoConfig>(`/api/v1/repos/${id}/config`),
    putConfig: (id: string, cfg: RepoConfig) =>
      req<RepoConfig>(`/api/v1/repos/${id}/config`, { method: "PUT", body: JSON.stringify(cfg) }),
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

  admin: {
    llmTest: () => req<{ ok: boolean; model: string; latency_ms: number | null; error: string | null }>(
      "/api/v1/admin/llm/test", { method: "POST" }
    ),
    runs: () => req<Run[]>("/api/v1/runs"),
    audit: () => req<Array<Record<string, unknown>>>("/api/v1/audit"),
  },
};
