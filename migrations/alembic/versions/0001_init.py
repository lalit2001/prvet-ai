"""Initial schema — verbatim DDL from PRD §9.

Revision ID: 0001
Revises:
Create Date: 2026-08-02
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

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
    role            TEXT NOT NULL DEFAULT 'member',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, email)
);

CREATE TABLE forge_connections (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    forge_type      TEXT NOT NULL,
    base_url        TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    credential_ref  TEXT NOT NULL,
    webhook_secret_ref TEXT NOT NULL,
    capabilities    JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'active',
    last_verified_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE repositories (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    connection_id   UUID NOT NULL REFERENCES forge_connections(id) ON DELETE CASCADE,
    external_id     TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    clone_url       TEXT NOT NULL,
    default_branch  TEXT NOT NULL DEFAULT 'main',
    primary_language TEXT,
    size_kb         BIGINT,
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    config          JSONB NOT NULL DEFAULT '{}',
    onboarded_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (connection_id, external_id)
);
CREATE INDEX ON repositories (org_id, is_enabled);

CREATE TABLE runs (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    run_type        TEXT NOT NULL,
    trigger         TEXT NOT NULL,
    status          TEXT NOT NULL,
    commit_sha      TEXT NOT NULL,
    base_sha        TEXT,
    pr_number       INTEGER,
    idempotency_key TEXT NOT NULL,
    runner_tier     TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     INTEGER,
    error           JSONB,
    stats           JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (idempotency_key)
);
CREATE INDEX ON runs (repo_id, run_type, created_at DESC);
CREATE INDEX ON runs (status) WHERE status IN ('queued','running');

CREATE TABLE baselines (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    run_id          UUID NOT NULL REFERENCES runs(id),
    commit_sha      TEXT NOT NULL,
    storage_uri     TEXT NOT NULL,
    metrics         JSONB NOT NULL,
    finding_count   INTEGER NOT NULL DEFAULT 0,
    is_current      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ON baselines (repo_id) WHERE is_current;

CREATE TABLE files (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    language        TEXT,
    content_hash    TEXT NOT NULL,
    loc             INTEGER,
    indexed_at_sha  TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repo_id, path)
);

CREATE TABLE symbols (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_id         UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    symbol_key      TEXT NOT NULL,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    signature       TEXT,
    visibility      TEXT,
    start_line      INTEGER NOT NULL,
    end_line        INTEGER NOT NULL,
    docstring       TEXT,
    precision       TEXT NOT NULL DEFAULT 'heuristic',
    UNIQUE (repo_id, symbol_key)
);
CREATE INDEX ON symbols (repo_id, name);
CREATE INDEX ON symbols (file_id);

CREATE TABLE symbol_references (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    from_symbol_id  UUID REFERENCES symbols(id) ON DELETE CASCADE,
    to_symbol_id    UUID NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    file_id         UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    line            INTEGER NOT NULL,
    ref_kind        TEXT NOT NULL,
    precision       TEXT NOT NULL DEFAULT 'heuristic'
);
CREATE INDEX ON symbol_references (to_symbol_id);
CREATE INDEX ON symbol_references (from_symbol_id);
CREATE INDEX ON symbol_references (repo_id, file_id);

CREATE TABLE code_chunks (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_id         UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    symbol_id       UUID REFERENCES symbols(id) ON DELETE SET NULL,
    start_line      INTEGER NOT NULL,
    end_line        INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(1024),
    token_count     INTEGER
);
CREATE INDEX ON code_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE findings (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    fingerprint     TEXT NOT NULL,
    source          TEXT NOT NULL,
    rule_id         TEXT,
    category        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    confidence      NUMERIC(3,2) NOT NULL DEFAULT 0.80,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    start_line      INTEGER,
    end_line        INTEGER,
    suggested_patch TEXT,
    affected_symbols JSONB NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'open',
    resolution      JSONB,
    posted_comment_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON findings (repo_id, fingerprint);
CREATE INDEX ON findings (run_id, severity);
CREATE INDEX ON findings (repo_id, status) WHERE status = 'open';

CREATE TABLE gate_decisions (
    id              UUID PRIMARY KEY,
    repo_id         UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    pr_number       INTEGER NOT NULL,
    commit_sha      TEXT NOT NULL,
    decision        TEXT NOT NULL,
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
    actor_external_id TEXT NOT NULL,
    actor_user_id   UUID REFERENCES users(id),
    actor_role      TEXT NOT NULL,
    reason          TEXT NOT NULL,
    findings_waived JSONB NOT NULL,
    approved_by     UUID REFERENCES users(id),
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON bypasses (repo_id, created_at DESC);

CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID NOT NULL,
    actor_type      TEXT NOT NULL,
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

CREATE TABLE llm_calls (
    id              UUID PRIMARY KEY,
    run_id          UUID REFERENCES runs(id) ON DELETE CASCADE,
    model           TEXT NOT NULL,
    purpose         TEXT NOT NULL,
    prompt_tokens   INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd        NUMERIC(10,6),
    latency_ms      INTEGER,
    cache_hit       BOOLEAN NOT NULL DEFAULT false,
    status          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON llm_calls (created_at DESC);

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
"""

DDL_DOWN = """
DROP TABLE IF EXISTS webhook_events, llm_calls, audit_log, bypasses, gate_decisions,
    findings, code_chunks, symbol_references, symbols, files, baselines, runs,
    repositories, forge_connections, users, organizations CASCADE;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DDL_DOWN)
