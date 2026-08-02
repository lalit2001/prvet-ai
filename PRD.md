# Product Requirements Document
# Sentry Review — Self-Hosted AI Code Review Platform

**Doc version:** 1.0
**Status:** Approved for implementation
**Codename / CLI binary:** `crv`
**Target audience of this document:** implementing engineers and coding agents. Everything here is meant to be executable without further clarification. Where a decision is genuinely open, it is listed in §20 — do not silently invent an answer to those.

---

## 1. Problem Statement

Code review is the highest-leverage quality gate in software engineering and the most poorly served by tooling. Existing AI review products (CodeRabbit, Greptile, Qodo) are SaaS-only: source code must leave the network. Regulated industries — banking, defence, healthcare, public sector — cannot use them at any price. Existing self-hosted tools (SonarQube, Semgrep) are rule-based and produce high-volume, low-context findings that teams learn to ignore.

Additionally, every AI review tool on the market reviews **the diff in isolation**. A change to a function signature is reviewed without knowing that 47 call sites exist across 12 modules. This is the single largest source of missed defects in automated review.

## 2. Product Goals

| # | Goal | Measured by |
|---|---|---|
| G1 | Run entirely inside the customer's network, including airgapped | Zero outbound connections required in `airgap` mode |
| G2 | Review changes **with their blast radius**, not in isolation | ≥90% of changed public symbols have their reverse-references included in LLM context |
| G3 | Findings developers act on | ≥40% of `high`/`critical` findings resolved before merge; <15% marked "not useful" |
| G4 | Block merges on unresolved issues, with auditable bypass | 100% of bypasses have actor + reason + timestamp recorded |
| G5 | Any LLM, no vendor lock | Switching model = one config change, zero code change |
| G6 | Deploy in under 10 minutes on any target | `crv init && crv deploy` → first PR comment |

## 3. Non-Goals (v1)

Explicitly out of scope. Do not build these.

- Auto-fixing and auto-committing code without human approval
- IDE plugins
- Test generation
- Code search UI (Sourcegraph-style)
- Multi-tenant SaaS billing, metering, or usage plans
- Languages beyond the Tier-1 set (§8.2)
- Mobile app
- Chat interface over the codebase

## 4. Personas

| Persona | Needs | Primary surface |
|---|---|---|
| **Developer (Dana)** | Fast, specific, non-noisy PR feedback; a way to dismiss wrong findings | PR comments in GitHub/GitLab |
| **Tech Lead (Tom)** | Enforce standards; see debt trends; unblock urgent releases | Weekly report + bypass |
| **Platform Engineer (Priya)** | Deploy it, keep it up, control spend | CLI + admin UI |
| **Security/Compliance (Sam)** | Prove nothing left the network; audit every override | Audit log + airgap mode |

## 5. Glossary

| Term | Definition |
|---|---|
| **Forge** | A git hosting platform: GitHub, GitLab, Azure DevOps, Bitbucket, Gitea |
| **Baseline** | Immutable snapshot of a repo's full analysis at a point in time |
| **Symbol** | A named code entity: function, class, method, interface, constant, type |
| **Reference** | An edge from a use-site to a symbol definition |
| **Blast radius** | The set of symbols transitively affected by a change, to depth N |
| **Finding** | One issue: rule/LLM-generated, with severity, location, and optional suggested patch |
| **Fingerprint** | Stable content-derived ID for a finding, invariant to line-number shifts |
| **Gate** | The pass/fail status posted to the forge that can block merge |
| **Bypass** | An authorised override of a failing gate |
| **Context pack** | The assembled prompt input for one LLM review call |

---

## 6. System Architecture

Six deployable components. All stateless except datastores.

```
 ┌────────────────────────────────────────────────────────────┐
 │ FORGES: GitHub · GitLab · Azure DevOps · Bitbucket · Gitea │
 └────────────┬───────────────────────────────▲───────────────┘
              │ webhook                       │ comments, status
              ▼                               │
 ┌──────────────────────┐            ┌────────┴──────────┐
 │ 1. API / Gateway     │            │ 5. Forge Adapters │
 │ FastAPI              │            │ (library, in-proc)│
 │ · HMAC verify        │            └────────▲──────────┘
 │ · REST + SSE         │                     │
 │ · OIDC + RBAC        │                     │
 └────────┬─────────────┘                     │
          │ enqueue                           │
          ▼                                   │
 ┌──────────────────────┐                     │
 │ 2. Queue             │                     │
 └────────┬─────────────┘                     │
          ▼                                   │
 ┌──────────────────────┐   ┌─────────────────┴──┐
 │ 3. Orchestrator      │──▶│ 4. Workers         │
 │ · job DAG            │   │ · indexer          │
 │ · escalation logic   │   │ · analyzer         │
 │ · idempotency        │   │ · reporter         │
 └────────┬─────────────┘   └─────────┬──────────┘
          │                           │
          ▼                           ▼
 ┌────────────────────┐    ┌────────────────────────┐
 │ Postgres+pgvector  │    │ 6. LLM Gateway         │
 │ Object store       │    │ (LiteLLM, OpenAI-compat)│
 └────────────────────┘    └────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
        vLLM / Ollama         Anthropic / OpenAI      Bedrock / Vertex
```

### 6.1 Component Responsibilities

| # | Component | Responsibility | Must NOT do |
|---|---|---|---|
| 1 | **API** | Receive webhooks, verify signatures, authn/authz, serve REST/SSE, enqueue jobs | Any analysis work; any LLM call; any git operation |
| 2 | **Queue** | Durable at-least-once delivery, DLQ | — |
| 3 | **Orchestrator** | Expand events into job DAGs, decide runner tier, enforce idempotency, budget checks | Long-running compute |
| 4 | **Workers** | Clone, index, analyse, call LLM, post results | Accept inbound HTTP |
| 5 | **Forge Adapters** | Normalise all forge APIs behind one interface | Contain business logic |
| 6 | **LLM Gateway** | Single OpenAI-compatible endpoint, routing, retries, cost accounting | Prompt construction |

**Hard rule:** the API must return HTTP 202 to a webhook within 500ms. All work is asynchronous. A webhook handler that performs analysis inline is a defect.

---

## 7. Repository Layout

Monorepo. `uv` for Python, `pnpm` for frontend, `go` for CLI.

```
sentry-review/
├── apps/
│   ├── api/                       # FastAPI — component 1
│   │   ├── src/crv_api/
│   │   │   ├── main.py
│   │   │   ├── routers/           # webhooks, repos, findings, reports, admin, auth
│   │   │   ├── deps.py            # DI: db session, current_user, settings
│   │   │   ├── middleware/        # request_id, logging, ratelimit
│   │   │   └── schemas/           # pydantic request/response models
│   │   └── tests/
│   ├── worker/                    # components 3 + 4
│   │   ├── src/crv_worker/
│   │   │   ├── orchestrator.py    # DAG expansion, escalation decision
│   │   │   ├── jobs/              # baseline.py, pr_review.py, weekly.py, index.py
│   │   │   ├── indexing/          # treesitter.py, scip.py, graph.py, chunker.py
│   │   │   ├── analysis/          # semgrep.py, gitleaks.py, osv.py, llm_review.py
│   │   │   ├── context/           # blast_radius.py, packer.py, budget.py
│   │   │   └── reporting/         # comment_builder.py, weekly_report.py
│   │   └── tests/
│   └── web/                       # Next.js 15 — admin UI
│       ├── app/
│       ├── components/
│       └── lib/
├── packages/
│   ├── core/                      # shared Python: models, settings, errors
│   │   └── src/crv_core/
│   │       ├── settings.py        # pydantic-settings, ALL env vars
│   │       ├── models/            # SQLAlchemy ORM
│   │       ├── domain/            # Finding, Symbol, ContextPack dataclasses
│   │       └── errors.py
│   ├── adapters/                  # THE PORTABILITY LAYER
│   │   └── src/crv_adapters/
│   │       ├── forge/             # base.py, github.py, gitlab.py, azdo.py, ...
│   │       ├── storage/           # base.py, s3.py, azure_blob.py, gcs.py, fs.py
│   │       ├── queue/             # base.py, sqs.py, servicebus.py, pubsub.py, redis.py, pg.py
│   │       ├── runner/            # base.py, local.py, docker.py, ecs.py, aci.py, k8s.py
│   │       ├── secrets/           # base.py, env.py, aws_sm.py, keyvault.py, vault.py
│   │       └── llm.py             # OpenAI-compatible client
│   └── rules/                     # bundled semgrep rules + custom rule schema
├── cli/                           # Go binary `crv`
│   ├── cmd/
│   ├── internal/{config,creds,deploy,doctor,tui}
│   └── embed/                     # go:embed of terraform + compose + helm
├── deploy/                        # per DEPLOYMENT PLAN doc
│   ├── terraform/modules/
│   ├── helm/codereview/
│   └── compose/
├── migrations/                    # alembic
├── docs/
└── docker/
    ├── api.Dockerfile
    ├── worker.Dockerfile          # slim — no build toolchains
    ├── indexer.Dockerfile         # fat — JDK, Node, Go, Cargo for SCIP
    └── web.Dockerfile
```

**Import boundary rule, enforced in CI:** no `boto3`, `azure.*`, `google.cloud.*`, `kubernetes` import may appear outside `packages/adapters/`. Implement as a `ruff` custom check or an import-linter contract. A violation fails the build.

---

## 8. Technology Decisions

### 8.1 Stack

| Layer | Choice | Version | Rationale |
|---|---|---|---|
| API | FastAPI + uvicorn | 0.115+ | Async, OpenAPI generation free |
| ORM | SQLAlchemy 2.0 async + Alembic | 2.0+ | Mature async support |
| Validation | Pydantic v2 / pydantic-settings | 2.9+ | Settings validation at boot |
| Worker | arq (Redis) or native queue adapter | — | Must work with SQS/PubSub too — see §11.3 |
| DB | PostgreSQL + pgvector | 16+ / 0.7+ | One datastore for metadata, graph, vectors |
| Parsing | tree-sitter + py-tree-sitter | 0.23+ | 40+ grammars, no build step |
| Precise xrefs | SCIP indexers | latest | Opt-in per language |
| SAST | Semgrep OSS | 1.90+ | Deterministic pre-filter |
| Secrets scan | gitleaks | 8.x | |
| Deps | osv-scanner | 1.9+ | |
| LLM proxy | LiteLLM | 1.5x+ | 100+ providers, OpenAI-compatible |
| Frontend | Next.js (App Router) + TypeScript | 15 | Static export capable for S3 hosting |
| UI kit | Tailwind + shadcn/ui | — | |
| CLI | Go + Cobra + Bubbletea + terraform-exec | 1.23+ | Single static binary |
| Observability | OpenTelemetry SDK, structlog | — | Vendor-neutral |
| Tests | pytest, pytest-asyncio, testcontainers, vitest | — | |

### 8.2 Language Support Tiers

| Tier | Languages | Capability |
|---|---|---|
| **Tier 1** (v1) | Python, TypeScript/JavaScript, Java, Go | tree-sitter symbols + SCIP precise xrefs + full rule coverage |
| **Tier 2** (v1) | C#, Ruby, PHP, Rust, Kotlin, C/C++ | tree-sitter symbols only (heuristic xrefs), full LLM review |
| **Tier 3** (v1) | Everything tree-sitter supports | LLM review on diff only, no blast radius |

The system must degrade gracefully: an unknown language gets a diff-only review, never an error.

---

## 9. Data Model

Full DDL. `pgvector` extension required. All tables use `uuid` PKs generated app-side (UUIDv7 preferred for index locality).

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Tenancy & identity ────────────────────────────────────
CREATE TABLE organizations (
    id              UUID PRIMARY KEY,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    settings        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    display_name    TEXT,
    oidc_subject    TEXT UNIQUE,
    role            TEXT NOT NULL DEFAULT 'member',  -- admin|maintainer|member|viewer
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, email)
);

-- ── Forge connections ─────────────────────────────────────
CREATE TABLE forge_connections (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    forge_type      TEXT NOT NULL,          -- github|gitlab|azure_devops|bitbucket|gitea
    base_url        TEXT NOT NULL,          -- https://api.github.com or self-hosted
    display_name    TEXT NOT NULL,
    credential_ref  TEXT NOT NULL,          -- key into SecretsAdapter, never the secret
    webhook_secret_ref TEXT NOT NULL,
    capabilities    JSONB NOT NULL DEFAULT '{}',  -- {"external_status_checks": false, "tier": "premium"}
    status          TEXT NOT NULL DEFAULT 'active',
    last_verified_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Repositories ──────────────────────────────────────────
CREATE TABLE repositories (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    connection_id   UUID NOT NULL REFERENCES forge_connections(id) ON DELETE CASCADE,
    external_id     TEXT NOT NULL,          -- forge's own repo id
    full_name       TEXT NOT NULL,          -- org/repo
    clone_url       TEXT NOT NULL,
    default_branch  TEXT NOT NULL DEFAULT 'main',
    primary_language TEXT,
    size_kb         BIGINT,
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    config          JSONB NOT NULL DEFAULT '{}',   -- per-repo overrides, see §14
    onboarded_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (connection_id, external_id)
);
CREATE INDEX ON repositories (org_id, is_enabled);

-- ── Analysis runs ─────────────────────────────────────────
CREATE TABLE runs (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    run_type        TEXT NOT NULL,          -- baseline|pr_review|weekly_drift|manual
    trigger         TEXT NOT NULL,          -- webhook|schedule|api|cli
    status          TEXT NOT NULL,          -- queued|running|succeeded|failed|cancelled|escalated
    commit_sha      TEXT NOT NULL,
    base_sha        TEXT,                   -- for pr_review / weekly_drift
    pr_number       INTEGER,
    idempotency_key TEXT NOT NULL,
    runner_tier     TEXT,                   -- fast|heavy
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     INTEGER,
    error           JSONB,
    stats           JSONB NOT NULL DEFAULT '{}',  -- files, symbols, tokens, cost_usd
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (idempotency_key)
);
CREATE INDEX ON runs (repo_id, run_type, created_at DESC);
CREATE INDEX ON runs (status) WHERE status IN ('queued','running');

-- ── Baselines ─────────────────────────────────────────────
CREATE TABLE baselines (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    run_id          UUID NOT NULL REFERENCES runs(id),
    commit_sha      TEXT NOT NULL,
    storage_uri     TEXT NOT NULL,          -- object store path to the snapshot archive
    metrics         JSONB NOT NULL,         -- loc, files, complexity, coverage, debt_score
    finding_count   INTEGER NOT NULL DEFAULT 0,
    is_current      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ON baselines (repo_id) WHERE is_current;

-- ── Symbol graph ──────────────────────────────────────────
CREATE TABLE files (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    language        TEXT,
    content_hash    TEXT NOT NULL,          -- sha256 of file content
    loc             INTEGER,
    indexed_at_sha  TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repo_id, path)
);

CREATE TABLE symbols (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_id         UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    symbol_key      TEXT NOT NULL,          -- stable: "py::pkg.mod.Class.method"
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,          -- function|method|class|interface|const|type|var
    signature       TEXT,
    visibility      TEXT,                   -- public|private|protected|internal
    start_line      INTEGER NOT NULL,
    end_line        INTEGER NOT NULL,
    docstring       TEXT,
    precision       TEXT NOT NULL DEFAULT 'heuristic',  -- precise (SCIP) | heuristic (tree-sitter)
    UNIQUE (repo_id, symbol_key)
);
CREATE INDEX ON symbols (repo_id, name);
CREATE INDEX ON symbols (file_id);

CREATE TABLE symbol_references (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    from_symbol_id  UUID REFERENCES symbols(id) ON DELETE CASCADE,   -- null = module-level use
    to_symbol_id    UUID NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    file_id         UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    line            INTEGER NOT NULL,
    ref_kind        TEXT NOT NULL,          -- call|import|inherit|implement|read|write|type_ref
    precision       TEXT NOT NULL DEFAULT 'heuristic'
);
CREATE INDEX ON symbol_references (to_symbol_id);    -- THE hot path: reverse refs
CREATE INDEX ON symbol_references (from_symbol_id);
CREATE INDEX ON symbol_references (repo_id, file_id);

-- ── Embeddings ────────────────────────────────────────────
CREATE TABLE code_chunks (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_id         UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    symbol_id       UUID REFERENCES symbols(id) ON DELETE SET NULL,
    start_line      INTEGER NOT NULL,
    end_line        INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(1024),           -- dimension from EMBEDDING_DIM, see §14
    token_count     INTEGER
);
CREATE INDEX ON code_chunks USING hnsw (embedding vector_cosine_ops);

-- ── Findings ──────────────────────────────────────────────
CREATE TABLE findings (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    fingerprint     TEXT NOT NULL,          -- stable across line moves, see §12.4
    source          TEXT NOT NULL,          -- semgrep|gitleaks|osv|llm|custom
    rule_id         TEXT,
    category        TEXT NOT NULL,          -- security|bug|performance|maintainability|style|dependency|test
    severity        TEXT NOT NULL,          -- critical|high|medium|low|info
    confidence      NUMERIC(3,2) NOT NULL DEFAULT 0.80,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,          -- markdown
    file_path       TEXT NOT NULL,
    start_line      INTEGER,
    end_line        INTEGER,
    suggested_patch TEXT,                   -- unified diff or replacement block
    affected_symbols JSONB NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'open',  -- open|resolved|dismissed|bypassed|stale
    resolution      JSONB,                  -- {by, at, reason, method}
    posted_comment_id TEXT,                 -- forge comment id, for updates/resolution
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON findings (repo_id, fingerprint);
CREATE INDEX ON findings (run_id, severity);
CREATE INDEX ON findings (repo_id, status) WHERE status = 'open';

-- ── Gate & bypass ─────────────────────────────────────────
CREATE TABLE gate_decisions (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    pr_number       INTEGER NOT NULL,
    commit_sha      TEXT NOT NULL,
    decision        TEXT NOT NULL,          -- pass|fail|neutral|error
    blocking_count  INTEGER NOT NULL DEFAULT 0,
    reason          TEXT,
    posted_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bypasses (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    pr_number       INTEGER NOT NULL,
    commit_sha      TEXT NOT NULL,
    actor_external_id TEXT NOT NULL,        -- forge username
    actor_user_id   UUID REFERENCES users(id),
    actor_role      TEXT NOT NULL,          -- role verified server-side at bypass time
    reason          TEXT NOT NULL,
    findings_waived JSONB NOT NULL,         -- array of finding ids + fingerprints
    approved_by     UUID REFERENCES users(id),   -- second approver, if required
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON bypasses (repo_id, created_at DESC);

-- ── Audit (append-only) ───────────────────────────────────
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID NOT NULL,
    actor_type      TEXT NOT NULL,          -- user|system|forge
    actor_id        TEXT,
    action          TEXT NOT NULL,
    resource_type   TEXT NOT NULL,
    resource_id     TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    ip_address      INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON audit_log (org_id, created_at DESC);
CREATE INDEX ON audit_log (action, created_at DESC);
-- Revoke UPDATE/DELETE from the application role on this table.

-- ── LLM accounting ────────────────────────────────────────
CREATE TABLE llm_calls (
    id              UUID PRIMARY KEY,
    run_id          UUID REFERENCES runs(id) ON DELETE CASCADE,
    model           TEXT NOT NULL,
    purpose         TEXT NOT NULL,          -- review|summarize|triage|embed
    prompt_tokens   INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd        NUMERIC(10,6),
    latency_ms      INTEGER,
    cache_hit       BOOLEAN NOT NULL DEFAULT false,
    status          TEXT NOT NULL,          -- ok|error|timeout|budget_exceeded
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON llm_calls (created_at DESC);

-- ── Webhook inbox (idempotency + replay) ──────────────────
CREATE TABLE webhook_events (
    id              UUID PRIMARY KEY,
    connection_id   UUID NOT NULL REFERENCES forge_connections(id) ON DELETE CASCADE,
    external_event_id TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    signature_valid BOOLEAN NOT NULL,
    processed_at    TIMESTAMPTZ,
    run_id          UUID REFERENCES runs(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (connection_id, external_event_id)
);
```

### 9.1 Retention

| Table | Retention | Mechanism |
|---|---|---|
| `webhook_events` | 30 days | Nightly delete job |
| `runs`, `findings` | 365 days | Configurable, `RETENTION_DAYS` |
| `llm_calls` | 90 days aggregated to daily rollup | Nightly rollup job |
| `audit_log` | Never deleted | Export to object store yearly |
| `code_chunks`, `symbols` | Current index only | Replaced on reindex |

---

## 10. Adapter Interfaces

These are contracts. Implement exactly. All are `Protocol` classes in `packages/adapters`.

### 10.1 ForgeAdapter

```python
# packages/adapters/src/crv_adapters/forge/base.py
from typing import Protocol, Literal
from dataclasses import dataclass

@dataclass(frozen=True)
class DiffHunk:
    file_path: str
    old_path: str | None          # set on rename
    change_type: Literal["added", "modified", "deleted", "renamed"]
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    content: str                  # raw unified diff hunk

@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    description: str
    author_external_id: str
    source_branch: str
    target_branch: str
    head_sha: str
    base_sha: str
    is_draft: bool
    labels: list[str]

@dataclass(frozen=True)
class ReviewComment:
    file_path: str
    line: int                     # line in the NEW file
    body: str                     # markdown
    suggestion: str | None        # if set, rendered as a native suggestion block

class ForgeAdapter(Protocol):
    forge_type: str

    async def verify_webhook(self, headers: dict[str, str], body: bytes, secret: str) -> bool:
        """Constant-time signature verification. MUST NOT be bypassable."""

    def parse_event(self, headers: dict[str, str], payload: dict) -> "ForgeEvent | None":
        """Return None for events we don't handle — do not raise."""

    async def get_pull_request(self, repo: str, number: int) -> PullRequest: ...

    async def get_diff(self, repo: str, base_sha: str, head_sha: str) -> list[DiffHunk]: ...

    async def get_file_content(self, repo: str, path: str, ref: str) -> bytes | None:
        """None if file does not exist at that ref."""

    async def post_review(
        self, repo: str, pr: int, commit_sha: str,
        summary: str, comments: list[ReviewComment],
    ) -> dict[str, str]:
        """Returns {comment_key: external_comment_id} for later updates.
        MUST batch into a single review where the forge supports it."""

    async def update_comment(self, repo: str, comment_id: str, body: str) -> None: ...
    async def resolve_thread(self, repo: str, comment_id: str) -> None: ...

    async def set_status(
        self, repo: str, commit_sha: str,
        state: Literal["pending", "success", "failure", "neutral"],
        title: str, summary: str, details_url: str,
    ) -> None: ...

    async def get_user_permission(self, repo: str, external_user_id: str) -> str:
        """Returns admin|maintain|write|read|none. MUST query the forge live —
        never trust a role asserted in a comment payload."""

    async def supports(self, capability: str) -> bool:
        """Capabilities: external_status_check, suggestion_blocks, resolve_thread,
        batch_review, draft_pr_events."""

    async def get_clone_credentials(self, repo: str) -> tuple[str, str]:
        """(username, token) — short-lived where the forge supports it."""
```

**Per-forge notes the implementer must handle:**

| Forge | Gotcha |
|---|---|
| GitHub | Use GitHub App with installation tokens (1h TTL), not PATs. Checks API for status. `POST /pulls/{n}/reviews` batches comments — use it, one comment per API call will hit rate limits. |
| GitLab | External Status Checks are **Ultimate-only**. `supports("external_status_check")` must return the real answer by probing `/api/v4/projects/{id}/external_status_checks` and checking for 403/404. Fallback: a CI job that fails. Discussion API differs from Notes API — use Discussions for resolvable threads. |
| Azure DevOps | PR Status API + branch policy of type `Status`. Policy must pre-exist or be created via the Policy Configuration API during onboarding. Threads API for comments. |
| Bitbucket | Reports API for annotations; 1000-annotation cap per report. |
| Gitea | Mostly GitHub-compatible; no Checks API — use commit statuses. |

### 10.2 Other Adapters

```python
class StorageAdapter(Protocol):
    async def put(self, key: str, data: bytes | AsyncIterator[bytes], content_type: str = ...) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def get_stream(self, key: str) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def presign_get(self, key: str, ttl_seconds: int = 3600) -> str: ...
    async def list(self, prefix: str) -> AsyncIterator[str]: ...

class QueueAdapter(Protocol):
    async def publish(self, topic: str, message: dict, dedup_key: str | None = None) -> str: ...
    async def consume(self, topic: str, max_messages: int = 1, visibility_s: int = 900) -> list["QueueMessage"]: ...
    async def ack(self, message: "QueueMessage") -> None: ...
    async def nack(self, message: "QueueMessage", requeue_after_s: int = 0) -> None: ...
    async def extend_visibility(self, message: "QueueMessage", seconds: int) -> None: ...

class JobRunner(Protocol):
    async def submit(self, job_spec: "JobSpec") -> str:
        """Returns an opaque job handle."""
    async def status(self, handle: str) -> Literal["pending","running","succeeded","failed"]: ...
    async def logs(self, handle: str, follow: bool = False) -> AsyncIterator[str]: ...
    async def cancel(self, handle: str) -> None: ...
    def capabilities(self) -> "RunnerCapabilities":
        """max_duration_s, max_memory_mb, max_disk_mb, supports_gpu"""

class SecretsAdapter(Protocol):
    async def get(self, ref: str) -> str: ...
    async def put(self, ref: str, value: str) -> None: ...
    async def delete(self, ref: str) -> None: ...
    async def rotate(self, ref: str) -> str: ...
```

**`JobRunner` is where escalation lives.** `LocalRunner` shells to a subprocess, `DockerRunner` to `docker run`, `EcsRunner` to `ecs:RunTask`, `K8sRunner` creates a `Job`, `LambdaRunner` invokes a function. The orchestrator picks a runner by comparing `JobSpec.estimated_requirements` against `runner.capabilities()`.

---

## 11. Feature Specifications

Each feature: user story → behaviour → acceptance criteria. Acceptance criteria are the test cases.

### F1 — Forge Connection & Webhooks

**Story:** As Priya, I connect our GitHub Enterprise instance once, and all webhook traffic is verified and routed.

**Behaviour**
1. Admin creates a connection in UI or via `crv` (forge type, base URL, credential).
2. System verifies credential by calling the forge's identity endpoint; stores credential via `SecretsAdapter`, never in Postgres.
3. System probes capabilities and persists them to `forge_connections.capabilities`.
4. Webhook endpoint: `POST /api/v1/webhooks/{connection_id}`.
5. Signature verified with `hmac.compare_digest`. On failure → 401, log to audit, **do not** process.
6. Event inserted into `webhook_events`. If `(connection_id, external_event_id)` already exists → return 200 immediately (duplicate delivery).
7. Enqueue job. Return **202** with `{"run_id": ...}`.

**Acceptance criteria**
- [ ] AC1.1 Invalid signature → 401, nothing enqueued, audit entry written
- [ ] AC1.2 Duplicate `X-GitHub-Delivery` → 200, exactly one run created
- [ ] AC1.3 P99 webhook response latency < 500 ms under 50 concurrent deliveries
- [ ] AC1.4 Unhandled event type (e.g. `star`) → 200, no run, no error log
- [ ] AC1.5 Payload > 5 MB is streamed to object store, pointer stored in `webhook_events.payload`
- [ ] AC1.6 GitLab connection on Free tier reports `external_status_check: false` and onboarding surfaces the CI-job fallback instructions
- [ ] AC1.7 Draft PR events are ignored unless `config.review_drafts` is true

### F2 — Repository Onboarding

**Story:** As Tom, I enable a repo and get a full baseline analysis without further action.

**Behaviour**
1. List repos from connection with pagination + search.
2. On enable: persist `repositories` row, register webhook on the forge (idempotent — check for existing hook first), create branch policy if the forge needs one, enqueue `baseline` run.
3. Read repo-level config from `.crv.yml` at the default branch if present (§14.2).
4. Emit an SSE progress stream the UI subscribes to.

**Acceptance criteria**
- [ ] AC2.1 Enabling a repo twice does not create duplicate webhooks
- [ ] AC2.2 Repo with no `.crv.yml` uses org defaults; malformed `.crv.yml` → repo enabled with defaults + a warning surfaced in the UI, never a hard failure
- [ ] AC2.3 Disabling a repo removes the forge webhook and cancels queued runs
- [ ] AC2.4 Archived / read-only repos cannot be enabled

### F3 — Indexing & Symbol Graph

**Story:** As the system, I build a queryable symbol graph so reviews can see blast radius.

**Behaviour**
1. Shallow clone (`--depth 1 --filter=blob:none` for the initial pass; full blobs fetched lazily per file).
2. Walk files; apply ignore rules: `.gitignore`, `.crvignore`, `config.exclude_paths`, binary detection, files > `MAX_FILE_KB` (default 1024), vendored paths (`vendor/`, `node_modules/`, `third_party/`, `dist/`, `*.min.js`, lockfiles).
3. For each file: detect language → parse with tree-sitter → extract symbols + references → upsert into `files`, `symbols`, `symbol_references`.
4. If SCIP is enabled and the language is Tier-1 and a build succeeds within `SCIP_TIMEOUT_S`, overlay precise references and mark `precision='precise'`. **SCIP failure must never fail the run** — fall back to heuristic and log.
5. Chunk code for embedding: prefer symbol-boundary chunks, fall back to 60-line sliding windows with 10-line overlap. Embed via the LLM gateway's embedding endpoint. Upsert `code_chunks`.
6. Incremental mode: given a list of changed paths, re-index only those files plus any file with a reference *into* a changed file.

**Acceptance criteria**
- [ ] AC3.1 100k-LOC Python repo indexes in < 4 min on 4 vCPU
- [ ] AC3.2 Re-indexing an unchanged repo is a no-op (all `content_hash` match) in < 15 s
- [ ] AC3.3 Incremental index of a 20-file change completes in < 20 s
- [ ] AC3.4 Symbol keys are stable across runs — a file moved with `git mv` retains reference edges
- [ ] AC3.5 A file in an unsupported language is recorded in `files` with `language=null` and does not break the run
- [ ] AC3.6 Syntax-error file → parse partial tree, record what is extractable, log warning, continue
- [ ] AC3.7 Memory ceiling: indexer never exceeds `INDEXER_MAX_MEMORY_MB`; it streams files rather than loading the repo
- [ ] AC3.8 SCIP indexer timeout or crash → run still succeeds with heuristic precision

### F4 — Day-1 Baseline Analysis

**Story:** As Tom, when I onboard a repo I get a full health report and a reference point for future comparisons.

**Behaviour**
1. Index the full repo (F3).
2. Run deterministic scanners across everything: Semgrep (bundled ruleset + custom), gitleaks, osv-scanner. These are cheap — run them on 100% of files.
3. Select **hotspots** for LLM review. Do NOT LLM the whole repo. Ranking function:
   ```
   score = 0.30*normalize(churn_90d)
         + 0.25*normalize(fan_in)          # reverse reference count
         + 0.20*normalize(cyclomatic)
         + 0.15*normalize(deterministic_finding_count)
         + 0.10*normalize(file_loc)
   ```
   Take the top `BASELINE_HOTSPOT_COUNT` files (default 150) subject to `BASELINE_MAX_COST_USD` (default 25).
4. LLM-review each hotspot file with surrounding context.
5. Compute metrics: LOC by language, avg/max complexity, test-file ratio, dependency count + known CVEs, coupling (avg fan-in/fan-out), duplication estimate, a 0–100 debt score.
6. Write snapshot archive to object store: `baselines/{repo_id}/{commit_sha}/snapshot.tar.zst` containing symbol graph export, findings JSON, metrics JSON, file manifest with hashes.
7. Mark `is_current = true`, unset the previous.
8. Render an HTML/markdown report; optionally open a summary issue on the forge.

**Acceptance criteria**
- [ ] AC4.1 Baseline on a 500k-LOC repo completes in < 45 min and under the configured cost ceiling
- [ ] AC4.2 Cost ceiling is enforced *before* spending — the run degrades hotspot count rather than overspending
- [ ] AC4.3 Snapshot archive is byte-reproducible given the same commit and config
- [ ] AC4.4 Baseline is resumable: killing the worker mid-run and restarting continues from the last completed stage
- [ ] AC4.5 Exactly one `is_current` baseline per repo, enforced by the partial unique index

### F5 — PR/MR Review with Blast Radius

**The core feature.** Read this section twice.

**Story:** As Dana, when I open a PR I get comments on my changes *and* on the places my changes will break.

**Behaviour**

*Stage 1 — Trigger.* On `pull_request.opened|synchronize|reopened` or GitLab `merge_request` equivalent. Debounce: if a new push arrives within `REVIEW_DEBOUNCE_S` (default 20) of a queued run for the same PR, cancel the older run.

*Stage 2 — Diff acquisition.* Fetch `base_sha..head_sha` diff. Skip files matching exclude rules. If the diff exceeds `MAX_DIFF_FILES` (default 500) or `MAX_DIFF_LINES` (default 20000), switch to summary-only mode and post a notice explaining why.

*Stage 3 — Incremental index.* Index changed files at `head_sha` into a scratch namespace so the mainline graph is unaffected.

*Stage 4 — Blast radius.* For each changed symbol:
```python
def blast_radius(symbol_id, depth=2, cap=40) -> list[Symbol]:
    """BFS over symbol_references, following to_symbol_id -> from_symbol_id (reverse).
    Rank results by:
      + 3 if reference crosses a module/package boundary
      + 2 if the referencing symbol is public
      + 2 if the changed symbol's signature changed (not just its body)
      + 1 if the referencing file has no adjacent test file
      - 2 if the referencing file is itself a test
    Return top `cap` by score. Deduplicate by file.
    """
```
Signature-change detection is important: a body-only change has a much smaller blast radius than a signature change, and treating them alike floods reviews with noise.

*Stage 5 — Deterministic analysis.* Semgrep/gitleaks/osv on changed files only.

*Stage 6 — Context pack assembly.* Per §13. Enforce `LLM_MAX_TOKENS_PER_PR`.

*Stage 7 — LLM review.* Structured JSON output per §13.2.

*Stage 8 — Filter & dedupe.*
- Drop findings below `MIN_CONFIDENCE` (default 0.6)
- Drop findings whose fingerprint matches an existing `dismissed` finding on this repo
- Drop findings on lines not in the diff **unless** category is `security` or the finding references a blast-radius symbol (these are the valuable cross-file findings — do not filter them out)
- Cap at `MAX_COMMENTS_PER_PR` (default 25), keeping highest severity × confidence
- Merge findings within 3 lines of each other into one comment

*Stage 9 — Post.* One batched review containing a summary comment + inline comments. Summary includes: what changed, risk assessment, blast-radius table, finding counts by severity, cost/duration footer.

*Stage 10 — Gate.* Per F7.

*Stage 11 — Re-review on push.* On `synchronize`: recompute; findings whose fingerprint disappeared → mark `resolved` and resolve the forge thread; findings that persist → do not repost, update the existing comment; new findings → post.

**Acceptance criteria**
- [ ] AC5.1 A PR changing a function signature produces a comment naming at least one affected caller in a different file
- [ ] AC5.2 A body-only change to the same function does NOT produce blast-radius comments
- [ ] AC5.3 Re-pushing with a fix resolves the thread and does not duplicate comments
- [ ] AC5.4 A 3-file PR is reviewed end-to-end in < 90 s (P50)
- [ ] AC5.5 Two rapid pushes result in exactly one posted review (debounce works)
- [ ] AC5.6 A 5000-file PR does not OOM and posts a summary-only notice
- [ ] AC5.7 Deleted file's symbols are removed from the scratch graph and referencing code is flagged
- [ ] AC5.8 A dismissed finding never reappears on the same repo
- [ ] AC5.9 Total comments never exceed the cap regardless of finding count
- [ ] AC5.10 If the LLM gateway is unreachable, the run posts a `neutral` status with an explanatory comment and does not block merge (when `GATE_MODE=fail_open`)

### F6 — Weekly Drift Report

**Story:** As Tom, every Monday I see what changed against the baseline and whether we improved.

**Behaviour**
1. Scheduled per repo (`config.weekly_schedule`, cron, default `0 6 * * MON` in repo timezone).
2. Load current baseline, diff `baseline.commit_sha..HEAD`.
3. Incremental index of changed files.
4. Re-run deterministic scanners on changed files; LLM only on hotspots *among the changes*.
5. Compare finding sets by fingerprint:
   - `new` — fingerprint absent from baseline
   - `resolved` — in baseline, absent now
   - `persisting` — in both, with an age counter
6. Compute metric deltas: LOC, complexity, coupling, dependency CVEs, debt score, test ratio.
7. Contributor view: findings introduced/resolved per author (present as team-level insight, **not** a leaderboard — this must be framed non-punitively or teams will disable it).
8. Render report; deliver by configured channels (UI, email, Slack/Teams webhook, forge issue).
9. If `config.auto_promote_baseline` is true, promote HEAD to the new baseline after the report.

**Acceptance criteria**
- [ ] AC6.1 A pure reformat (whitespace only) produces zero new findings — fingerprints are format-invariant
- [ ] AC6.2 A file renamed with no content change produces zero new findings
- [ ] AC6.3 Report renders correctly with zero changes in the week
- [ ] AC6.4 Missed schedule (system was down) runs on next startup, once, not N times
- [ ] AC6.5 Weekly run on a repo with no baseline triggers a baseline instead, and says so

### F7 — Merge Gate & Bypass

**Story:** As Tom, PRs with unresolved critical issues cannot merge, but I can override for a production hotfix and it is recorded.

**Behaviour**

*Gate evaluation:*
```python
blocking = [f for f in findings
            if severity_rank(f.severity) >= severity_rank(config.gate_block_severity)
            and f.confidence >= config.gate_min_confidence
            and f.status == "open"
            and f.category in config.gate_categories]

if active_bypass_exists(pr, head_sha):  decision = "pass"
elif blocking:                          decision = "fail"
elif run_errored and GATE_MODE == "fail_closed": decision = "fail"
elif run_errored:                       decision = "neutral"
else:                                   decision = "pass"
```

*Status posting:* GitHub → Checks API with `conclusion`. GitLab Ultimate → external status check. GitLab non-Ultimate → the customer's CI job calls `crv gate check --pr N` which exits non-zero. Azure DevOps → PR Status + policy.

*Bypass flow:*
1. Authorised user comments `/crv bypass reason: <text>` on the PR (minimum 20 characters of reason; reject shorter with a reply explaining why).
2. System calls `forge.get_user_permission()` **live** to verify the actor. Never trust the payload's claimed role.
3. Check the actor's role against `config.bypass_roles`.
4. If any waived finding is `critical` and `config.bypass_require_second_approver` is true → post a comment requesting a second authorised approver; do not apply until received.
5. Write the `bypasses` row and an `audit_log` entry.
6. Re-post gate as `pass` with a summary naming the actor and reason.
7. Bypass is scoped to `commit_sha`. A new push invalidates it. This is deliberate — it prevents "bypass then push anything".

**Acceptance criteria**
- [ ] AC7.1 Unauthorised user's bypass comment is rejected with an explanatory reply; no bypass row created
- [ ] AC7.2 Bypass with a fabricated role claim in the comment body is rejected (role comes from the forge API only)
- [ ] AC7.3 Pushing a new commit after a bypass re-blocks the PR
- [ ] AC7.4 Every bypass appears in the audit log with actor, reason, waived findings, and timestamp
- [ ] AC7.5 `GATE_MODE=fail_open` + LLM outage → `neutral` status, merge not blocked
- [ ] AC7.6 `GATE_MODE=fail_closed` + LLM outage → `failure` status with a clear reason
- [ ] AC7.7 Gate status is posted within 5 s of the review completing
- [ ] AC7.8 Bypass audit entries cannot be updated or deleted by the application DB role

### F8 — LLM Gateway & Model Routing

**Behaviour**
1. All model traffic goes through one OpenAI-compatible base URL. Application code never imports a provider SDK.
2. Two configured model roles: `LLM_MODEL_FAST` (style, docs, simple bugs, triage, summarisation) and `LLM_MODEL_DEEP` (security, architecture, blast-radius reasoning). Route by task, not by user preference.
3. Retries: 3 attempts, exponential backoff with jitter, on 429/5xx/timeout only.
4. Timeout: `LLM_TIMEOUT_S` default 120.
5. Prompt cache: hash of (system prompt + context pack) → response, TTL 24h, stored in the cache backend. Re-reviews of unchanged files are then free.
6. Budget: check `llm_calls` monthly spend before each call. At 80% → warn in UI and via webhook. At 100% → `budget_exceeded`, degrade to deterministic-only reviews, post a notice on PRs, do not silently stop reviewing.
7. Record every call in `llm_calls`.

**Acceptance criteria**
- [ ] AC8.1 Switching `LLM_MODEL_DEEP` from a hosted model to a local vLLM endpoint requires zero code change and no restart beyond config reload
- [ ] AC8.2 A malformed JSON response is retried once with a repair prompt, then the finding batch is dropped with a logged error — never crash the run
- [ ] AC8.3 Budget exceeded → deterministic findings still posted, gate still evaluated
- [ ] AC8.4 Cache hit rate > 30% on a repo with repeated CI pushes
- [ ] AC8.5 No provider SDK import exists outside `packages/adapters`

### F9 — Web UI

Routes and their required content:

| Route | Content |
|---|---|
| `/login` | OIDC redirect, or local login when `AUTH_MODE=local` |
| `/` | Org dashboard: repos, open findings by severity, weekly trend, spend this month |
| `/repos` | Table with search, enable/disable toggle, last run status |
| `/repos/[id]` | Health score, metric trend charts, baseline info, run history, per-repo config editor |
| `/repos/[id]/findings` | Filterable table (severity, category, status, path); bulk dismiss |
| `/runs/[id]` | Live SSE log stream, stage timeline, token/cost breakdown, produced findings |
| `/reports/[id]` | Rendered weekly report, exportable to PDF/markdown |
| `/admin/connections` | Forge connections, credential status, capability probe results |
| `/admin/models` | LLM endpoint config, model roles, budget, live connectivity test button |
| `/admin/rules` | Enable/disable rule packs, custom rule editor with live test-against-file |
| `/admin/audit` | Audit log with filters; bypass log prominent, exportable to CSV |
| `/admin/users` | Users, roles, invite |

**Requirements**
- Must build with `output: 'export'` for S3/Blob/GCS static hosting. No server-side rendering dependency, no Next.js API routes. The API base URL is injected at runtime via `window.__CRV_CONFIG__` from a `config.js` written at deploy time — **not** baked in at build time, or a single build cannot serve multiple deployments.
- Dark mode. Keyboard navigation on all tables. WCAG 2.1 AA.
- SSE for live run progress with polling fallback.

**Acceptance criteria**
- [ ] AC9.1 Static export deploys to an S3 bucket and functions fully against a Lambda API
- [ ] AC9.2 Changing the API URL requires editing `config.js` only, not rebuilding
- [ ] AC9.3 Findings table remains responsive with 10,000 rows (virtualised)
- [ ] AC9.4 Every destructive action has a confirmation naming the resource

### F10 — Observability

- Structured JSON logs (`structlog`), `request_id` and `run_id` on every line, secrets redacted by a filter.
- OpenTelemetry traces: one span per job stage; export OTLP to any collector.
- Prometheus metrics at `/metrics`: `crv_runs_total{type,status}`, `crv_run_duration_seconds`, `crv_findings_total{severity,source}`, `crv_llm_tokens_total{model,purpose}`, `crv_llm_cost_usd_total`, `crv_queue_depth`, `crv_webhook_latency_seconds`, `crv_gate_decisions_total{decision}`.
- Health endpoints: `/healthz` (liveness, no dependency checks), `/readyz` (checks DB, queue, storage, LLM).

