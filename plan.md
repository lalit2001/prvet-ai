# Delivery, Deployment & Cost Plan
# Sentry Review (`crv`) — Companion to PRD.md

**Doc version:** 1.0
**Reads with:** `PRD.md` (v1.0). This plan does not re-state the PRD; it fills the sections the PRD references but leaves open (§11, §12, §13, §14, §20), and adds a phased delivery plan, per-target deployment guides, per-SKU cost tables, and the single-command CLI flow.
**Target audience:** the implementing team + the coding agents that will build it.

> **Ponytail rule active for this project.** Every section here is the shortest thing that answers the question. Speculative flexibility gets called out and skipped. If a decision is a real judgment call it is listed in [§20 Open Decisions](#20-open-decisions) — do not silently invent one.

> **Surface split (non-negotiable):** the **CLI (`crv`) is a deployment helper only** — install, upgrade, health check, CI gate probe. **Everything else runs in the Web UI**: connecting forges, adding repos, configuring LLMs, editing rules, setting thresholds, viewing reports and findings, managing users. If a knob exists at runtime, it lives in the UI, not the CLI. See [§C5](#c5-the-crv-single-command-flow).

---

## Table of Contents

- [0. TL;DR](#0-tldr)
- [Part A — Delivery Plan](#part-a--delivery-plan)
  - [1. Milestones M0 → M6](#1-milestones-m0--m6)
  - [2. Team shape & effort](#2-team-shape--effort)
  - [3. Definition of done per milestone](#3-definition-of-done-per-milestone)
- [Part B — Missing PRD Sections](#part-b--missing-prd-sections)
  - [§11. Deployment Topology](#11-deployment-topology)
  - [§12. Finding Fingerprints](#12-finding-fingerprints)
  - [§13. Context Pack Assembly](#13-context-pack-assembly)
  - [§14. Configuration Matrix](#14-configuration-matrix)
  - [§20. Open Decisions Ledger](#20-open-decisions-ledger)
- [Part C — Deployment Guides](#part-c--deployment-guides)
  - [C1. Docker Compose (laptop + on-prem VM)](#c1-docker-compose-laptop--on-prem-vm)
  - [C2. AWS: Lambda + ECS Fargate + S3](#c2-aws-lambda--ecs-fargate--s3)
  - [C3. Azure: Container Apps + Static Web Apps + Service Bus](#c3-azure-container-apps--static-web-apps--service-bus)
  - [C4. Kubernetes Helm chart (cloud-agnostic + airgap)](#c4-kubernetes-helm-chart-cloud-agnostic--airgap)
  - [C5. The `crv` single-command flow](#c5-the-crv-single-command-flow)
- [Part D — Cost Model (per-SKU)](#part-d--cost-model-per-sku)
  - [D1. Sizing tiers](#d1-sizing-tiers)
  - [D2. AWS line items](#d2-aws-line-items)
  - [D3. Azure line items](#d3-azure-line-items)
  - [D4. On-prem / self-hosted](#d4-on-prem--self-hosted)
  - [D5. LLM operating cost](#d5-llm-operating-cost)
  - [D6. What drives cost up and how to stop it](#d6-what-drives-cost-up-and-how-to-stop-it)
- [Part E — Container Strategy](#part-e--container-strategy)
- [Part F — Risk Register](#part-f--risk-register)

---

## 0. TL;DR

- **Build order:** compose-first. If it does not run under `docker compose up`, it does not exist. Cloud targets wrap the same images. **No cloud-specific code paths outside `packages/adapters/`.**
- **Six deployable components** (per PRD §6), **four container images** (`api`, `worker`, `indexer`, `web`), **one CLI** (`crv`).
- **Delivery** in 7 milestones over ~26 engineer-weeks (≈13 weeks with a team of 2). MVP that can review a real PR on GitHub is M3 (~11 weeks).
- **Deploy targets:** Compose, AWS (Lambda API + ECS Fargate workers + S3/CloudFront web), Azure (Container Apps + SWA + Service Bus), Helm (any k8s). Each is one `crv deploy` command.
- **Cost floor (self-hosted):** one small VM + an OpenAI-compatible endpoint. Infra ≈ $25–40/mo, LLM ≈ $0.02–0.10 per PR reviewed with a hosted model, or effectively free with a local Ollama/vLLM.
- **Cost ceiling (production, mid-size org, 50 repos, 500 PRs/mo):** infra ≈ $350–800/mo depending on cloud, LLM ≈ $40–200/mo with caching.

---

## Part A — Delivery Plan

### 1. Milestones M0 → M6

Each milestone ends with a **demoable slice**. No milestone is "internal plumbing" — every one changes what a user can do. Weeks are engineer-weeks (1 IC full-time = 1 wk/wk).

| # | Milestone | Weeks | User-visible outcome |
|---|---|---:|---|
| **M0** | Monorepo & bootstrap | 1 | `git clone && make dev` starts postgres + a hello API + hello worker + a hello web page under compose. All CI green (lint, type, test on empty stubs). |
| **M1** | Forge round-trip on GitHub | 3 | GitHub webhook → 202 in <500ms → worker posts a hard-coded "hello from crv" review comment on the PR. Signature verified, replay-safe. No analysis yet. |
| **M2** | Indexer + baseline (Python + TS only) | 5 | `crv baseline <repo>` produces symbol graph + Semgrep + gitleaks + OSV findings + metrics snapshot in Postgres and object store. Web UI shows the baseline. |
| **M3** | PR review with blast radius (**MVP**) | 6 | Real GitHub PR gets real inline LLM comments referencing real callers. Gate posts pass/fail. `/crv bypass` works. This is the smallest thing worth shipping. |
| **M4** | GitLab + Azure DevOps + weekly drift | 4 | Same review flow, three forges. Monday morning: drift report renders in the UI and posts to a configured Slack/Teams webhook. |
| **M5** | Cloud deploys (AWS + Azure + Helm) | 4 | `crv deploy --target aws|azure|k8s` provisions the whole stack from a laptop. Static export web at `s3://` or Azure SWA. Same DB migration path. |
| **M6** | Hardening & airgap | 3 | Airgap mode passes an outbound-firewall test. OIDC + RBAC + audit-log export. Tier-1 SCIP precise xrefs land for Java + Go. Docs, threat model, release-1.0 tag. |

**Total: 26 engineer-weeks.** With 2 senior engineers: ~13 wall weeks. With 3: ~10.

**Not in v1** — deferred to v1.1 or later, per PRD §3 and to keep v1 shippable:
- Bitbucket + Gitea adapters (stubs land in M1; full support post-1.0).
- Tier-2 language SCIP indexers.
- Auto-fix PR generation.
- Multi-tenant billing.

### 2. Team shape & effort

Minimum viable team to hit M3 (MVP) in a quarter:

- **1 backend engineer** — Python, FastAPI, Postgres, adapters. Owns apps/api, apps/worker, packages/*.
- **1 full-stack engineer** — Next.js + Go CLI + Docker/Terraform/Helm. Owns apps/web, cli/, deploy/.
- **0.25 designer** (contract) — for the M3 review-comment format and the M4 weekly report. Everything else uses shadcn defaults.

Optional accelerators (each cuts ~2 weeks off M3–M6):

- **+1 platform engineer** for M5 (cloud deploys land in parallel with M4).
- **+1 security engineer** for M6 (threat model + airgap validation + OIDC).

### 3. Definition of done per milestone

A milestone is done when **every one** of these is true. If one isn't, the milestone isn't.

**Per milestone, always:**
- All acceptance criteria in the covered PRD F-sections are passing tests.
- `make check` green: `ruff`, `mypy --strict` on packages/core + adapters, `pytest`, `vitest`, `go test`, import-linter, `helm lint`, `terraform validate`.
- `docker compose up` from a fresh clone → the M-N demo works end-to-end.
- One page of user-facing docs in `docs/` for the shipped surface.

**Additional gates per milestone:**

| # | Additional exit criteria |
|---|---|
| M0 | Import-linter contract in place: `boto3`, `azure.*`, `google.cloud.*`, `kubernetes` importable only from `packages/adapters/`. A test asserts a violation fails CI. |
| M1 | Constant-time HMAC verified in a fuzz test. Duplicate `X-GitHub-Delivery` produces exactly one run (AC1.2). P99 webhook latency <500ms under 50 concurrent (AC1.3). |
| M2 | Baseline on the `django/django` repo (~500k LOC) finishes in <45 min on a 4-vCPU worker (AC4.1). Snapshot archive is byte-reproducible across two runs of the same SHA (AC4.3). |
| M3 | On a seeded PR that changes a function signature with a caller in another module, at least one comment names the caller by file:line (AC5.1). A body-only change to the same function produces zero blast-radius comments (AC5.2). Bypass with a fabricated role in the comment body is rejected (AC7.2). |
| M4 | Same PR fixture on GitHub, GitLab, and ADO produces equivalent comment sets (allowable delta: forge-specific rendering). Weekly drift on a repo with zero changes renders correctly and posts nothing new (AC6.3). |
| M5 | `crv deploy --target aws` from a laptop with fresh AWS creds → first PR comment in <15 min (G6). Same for `--target azure` and `--target k8s`. Rollback: `crv destroy` leaves no dangling resources. |
| M6 | Airgap mode: run the full test suite with outbound network blocked at the container level; every test passes. OWASP top-10 checklist reviewed and either mitigated or explicitly accepted in `docs/THREAT_MODEL.md`. |

---

## Part B — Missing PRD Sections

These sections are referenced from PRD.md but the PRD stops at §10/F10. They live here instead of forcing a PRD revision.

### §11. Deployment Topology

Six components (PRD §6) map to physical processes as follows. **The same container images are used in every topology** — differences are which adapter is selected and how many replicas run.

| Component | Compose | AWS | Azure | k8s (Helm) |
|---|---|---|---|---|
| **1. API** | `api` container | Lambda (container image) behind API Gateway HTTP API | Container Apps (min 1, max N) behind default ingress | `Deployment` behind `Ingress`, HPA on CPU |
| **2. Queue** | Redis (arq) | SQS (standard, FIFO for dedup) | Service Bus queue | Redis (bitnami chart) or NATS |
| **3. Orchestrator** | in-process in `worker` | in-process in worker task | in-process in worker container | in-process in worker pod |
| **4. Workers** | `worker` container × N | ECS Fargate service (long jobs) + Lambda (short jobs, optional) | Container Apps job (event-driven scale on Service Bus depth) | `Deployment` + KEDA scaler on queue depth |
| **5. Forge adapters** | in-process (library) | in-process | in-process | in-process |
| **6. LLM Gateway** | `litellm` container | ECS Fargate service **or** external endpoint | Container Apps service **or** external endpoint | `Deployment` **or** external endpoint |
| **DB** | `postgres` container | RDS Postgres 16 + pgvector | Azure Database for PostgreSQL Flexible Server | operator-managed or external |
| **Object store** | filesystem volume | S3 | Blob Storage | MinIO or external S3-compatible |
| **Secrets** | `.env` file mounted read-only | AWS Secrets Manager | Key Vault | Kubernetes `Secret` or external-secrets-operator → Vault |
| **Web** | `web` container | S3 static site + CloudFront | Static Web Apps | `nginx` sidecar or bundled with `api` chart |

**Non-negotiables that survive every topology:**

- The **API returns 202 in <500ms**. Any topology that puts synchronous work in the webhook path is wrong.
- The **web is a static export** (Next.js `output: 'export'`). API URL is injected at deploy time via a `config.js` written into the built artifact — never baked in at `next build`. This is what lets one `web` image serve every deploy.
- **All secrets live behind `SecretsAdapter`.** No `os.environ["OPENAI_API_KEY"]` outside `packages/adapters/secrets/env.py`.

**Runner escalation** (PRD §10.2 `JobRunner`): the orchestrator picks a runner by comparing `JobSpec.estimated_requirements` against `runner.capabilities()`. In compose the only runner is `LocalRunner`. In cloud, `LambdaRunner` handles jobs <15 min and <10 GB RAM (PR reviews, incremental indexes) and escalates to `EcsRunner`/`AciRunner`/`K8sJobRunner` for baselines and 500k-LOC reindexes.

### §12. Finding Fingerprints

A fingerprint is a stable content-derived ID for a finding. It must be invariant to formatting, line-number shifts, and file renames within reason, so that:

- Re-running on the same file with the same issue → same fingerprint (dedupe, PRD §11 F5 stage 8).
- A user who dismisses a finding → the same finding never returns (AC5.8).
- Whitespace-only reformats produce zero new fingerprints (AC6.1).
- A `git mv` produces zero new fingerprints (AC6.2).

**Algorithm:**

```
fingerprint = sha256(
    canonical_source     # normalized code excerpt: strip comments, collapse whitespace, lowercase keywords stripped of case-only diffs
  + "\x00"
  + rule_id or llm_category
  + "\x00"
  + symbol_key or ""     # PRD symbol_key when the finding attaches to a symbol; "" for file-level
  + "\x00"
  + canonical_message    # LLM message reduced to its "shape": first sentence, numerals replaced with N, quoted identifiers replaced with $ID
)[:16].hex()
```

- **Line numbers are not in the fingerprint.** Ever.
- **File paths are not in the fingerprint** *unless* the finding has no symbol_key (a top-level config-file finding). Renames of files that contain symbols do not disturb fingerprints because `symbol_key` follows the code, not the file.
- The `canonical_source` normalization runs the tree-sitter parse once, walks the AST, and pretty-prints a minimal token stream. This is language-aware: whitespace and comments never affect the hash. This is the *only* part of fingerprinting that is worth spending time on — everything else is a hash concatenation.

**Storage:** `findings.fingerprint` is a `TEXT` column with a b-tree index on `(repo_id, fingerprint)`. Dismissals live in `findings` with `status='dismissed'`; the dedupe query is `WHERE repo_id = ? AND fingerprint = ANY(?) AND status IN ('dismissed', 'open')`.

**ponytail: canonicalization is 60 lines per language, not a framework — extend when a real dedupe miss shows up.**

### §13. Context Pack Assembly

The **context pack** is the assembled prompt input for one LLM review call (PRD glossary). Getting this right is 80% of review quality. The goal: fit as much *relevant* code as possible into the model's context window without ever exceeding `LLM_MAX_TOKENS_PER_PR`.

**Pack structure (fed to the model as a single user message):**

```
<meta>
  repo, PR number, base_sha..head_sha, model role (fast|deep), budget remaining
</meta>

<pr>
  title, description (trimmed to 2000 chars), labels
</pr>

<diff>
  <hunk file="apps/api/src/crv_api/routers/webhooks.py" old_lines="..." new_lines="...">
    unified diff
  </hunk>
  ...
</diff>

<blast_radius>
  <symbol name="verify_webhook" file="apps/api/.../webhooks.py" kind="function" signature_changed="true">
    <caller file="apps/api/.../deps.py" line="47" excerpt_lines="6">
      ...code excerpt...
    </caller>
    ...
  </symbol>
</blast_radius>

<supporting_context>
  <file path="packages/adapters/src/crv_adapters/forge/base.py" reason="defines ForgeAdapter Protocol referenced by the change" excerpt_lines="30">...</file>
</supporting_context>

<deterministic_findings>
  semgrep/gitleaks/osv output, JSON, filtered to changed files
</deterministic_findings>

<review_guidelines>
  per-repo prompt overrides from .crv.yml
</review_guidelines>
```

**Assembly algorithm:**

```
budget = LLM_MAX_TOKENS_PER_PR - reserve_for_response
# order matters: fill the mandatory parts first, then extras until budget hits
1. meta + pr  (always fits, ~200 tok)
2. diff hunks, largest first, until 40% of budget used
3. blast_radius entries, ranked by the score in F5 stage 4, until 40% of budget used
   - each caller shows ±3 lines around the call site by default
   - if a caller is in an already-included diff hunk, skip (no duplicates)
4. supporting_context (imports, type defs, immediate parent class):
   - only for symbols in blast_radius or in the diff
   - vector-search retrieval only as a last-resort fallback, not a first pass
5. deterministic_findings (compact JSON, ~1000 tok)
6. review_guidelines (repo config, ~500 tok)
```

**§13.2 — LLM output schema.** The `deep` model is called with a JSON-mode/structured-output request. The response must match:

```json
{
  "summary": "One paragraph markdown. Risk level: LOW|MEDIUM|HIGH.",
  "findings": [
    {
      "category": "security|bug|performance|maintainability|style|dependency|test",
      "severity": "critical|high|medium|low|info",
      "confidence": 0.0,
      "file_path": "path/from/repo/root.py",
      "start_line": 42,
      "end_line": 47,
      "title": "One sentence.",
      "body": "Markdown. Explain the risk. Reference specific callers by file:line when relevant.",
      "suggested_patch": "unified diff or null",
      "affected_symbols": ["py::pkg.mod.func"]
    }
  ]
}
```

Any deviation → one retry with a repair prompt including the JSON schema and the model's malformed output (AC8.2). On second failure the batch is dropped, an error is logged, and the run continues — never crash.

### §14. Configuration Matrix

There are two layers of config, and one hard rule: **there is no third layer**. Runtime toggles and secrets are not the same thing, and both together are already too many places to look.

**Layer 1 — environment / deployment config.** Set once per deployment, via `.env`, Secrets Manager / Key Vault / Vault, or Helm values. Managed by Priya. Full list:

| Var | Default | What |
|---|---|---|
| `DEPLOYMENT_MODE` | `standard` | `standard` \| `airgap` — airgap fails any outbound to non-configured hosts |
| `DATABASE_URL` | — | Postgres 16 + pgvector, async DSN |
| `QUEUE_BACKEND` | `redis` | `redis` \| `sqs` \| `servicebus` \| `pubsub` \| `pg` |
| `QUEUE_URL` | — | connection string for the chosen backend |
| `STORAGE_BACKEND` | `fs` | `fs` \| `s3` \| `azure_blob` \| `gcs` |
| `STORAGE_URI` | `/var/lib/crv/objects` | bucket URI or FS path |
| `SECRETS_BACKEND` | `env` | `env` \| `aws_sm` \| `keyvault` \| `vault` |
| `RUNNER_BACKEND` | `local` | `local` \| `docker` \| `ecs` \| `aci` \| `k8s` \| `lambda` |
| `AUTH_MODE` | `local` | `local` \| `oidc` |
| `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET_REF` | — | required if `AUTH_MODE=oidc` |
| `LLM_BASE_URL` | — | OpenAI-compatible endpoint (Bedrock via LiteLLM, Azure OpenAI, vLLM, Ollama, Anthropic, OpenAI, etc.) |
| `LLM_API_KEY_REF` | — | secret ref, not the key |
| `LLM_MODEL_FAST` | `gpt-4o-mini` | style, summarization, triage |
| `LLM_MODEL_DEEP` | `claude-sonnet-4-6` | security + blast radius + architecture |
| `LLM_EMBEDDING_MODEL` | `text-embedding-3-small` | 1024-dim |
| `EMBEDDING_DIM` | `1024` | must match model; hard-fails at boot if it doesn't |
| `LLM_TIMEOUT_S` | `120` | per call |
| `LLM_MAX_TOKENS_PER_PR` | `120000` | context-pack ceiling |
| `LLM_MONTHLY_BUDGET_USD` | `500` | 80% warns, 100% degrades |
| `PROMPT_CACHE_BACKEND` | `redis` | `redis` \| `fs` \| `off` |
| `GATE_MODE` | `fail_open` | `fail_open` \| `fail_closed` on LLM outage |
| `GATE_BLOCK_SEVERITY` | `high` | inclusive floor for what blocks merge |
| `MAX_FILE_KB` | `1024` | file size ceiling for indexing |
| `MAX_DIFF_FILES` | `500` | above → summary-only |
| `MAX_DIFF_LINES` | `20000` | above → summary-only |
| `SCIP_TIMEOUT_S` | `300` | per language, per repo |
| `INDEXER_MAX_MEMORY_MB` | `2048` | worker RSS ceiling for indexing |
| `RETENTION_DAYS` | `365` | runs + findings |
| `BASELINE_HOTSPOT_COUNT` | `150` | LLM-reviewed files at baseline |
| `BASELINE_MAX_COST_USD` | `25` | baseline hard cap |
| `REVIEW_DEBOUNCE_S` | `20` | drops earlier runs on rapid push |
| `MIN_CONFIDENCE` | `0.6` | drops below this |
| `MAX_COMMENTS_PER_PR` | `25` | posts top-N by severity×confidence |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | optional; unset = no traces |
| `LOG_LEVEL` | `info` | `debug` \| `info` \| `warn` \| `error` |
| `TZ` | `UTC` | affects `weekly_schedule` cron |

**Layer 2 — per-repo config.** Committed to the repo as `.crv.yml` at the default branch (PRD F2). Managed by Dana/Tom. Malformed → repo enabled with defaults + a warning (AC2.2).

```yaml
# .crv.yml — checked into the repo, per-branch overrides via file at that ref
review:
  block_severity: high            # overrides GATE_BLOCK_SEVERITY for this repo
  categories: [security, bug, performance]   # gate only on these
  min_confidence: 0.7
  drafts: false                   # review draft PRs?
  guidelines: |
    Prefer async SQLAlchemy 2.0 over sync. Any new HTTP client must use httpx.

bypass:
  roles: [admin, maintain]        # forge roles allowed to bypass
  require_second_approver_for: [critical]

exclude_paths:
  - "vendor/**"
  - "**/*.generated.*"
  - "migrations/**/*.sql"

hotspots:
  count: 150
  extra: ["src/security/**", "src/payments/**"]  # always LLM-review, ignoring rank

weekly:
  schedule: "0 6 * * MON"
  auto_promote_baseline: false
  channels: [ui, forge_issue, "webhook:https://hooks.slack.com/..."]
```

**Precedence:** repo `.crv.yml` > org defaults > env defaults. That's the whole precedence stack. No third layer.

### §20. Open Decisions Ledger

Genuinely open — pick before starting the affected milestone. Silently inventing an answer is a defect.

| # | Decision | Blocks | Options | Recommendation |
|---|---|---|---|---|
| D1 | Local login backend for `AUTH_MODE=local` | M0 | argon2 in Postgres; delegate to `dex` / `authelia` sidecar | Argon2 in Postgres — one page of code, no extra process for the compose default |
| D2 | Queue in compose | M0 | `redis` + `arq`; `postgres` as queue via `SKIP LOCKED` | Redis + arq — arq is minimal and matches SQS/Service Bus semantics closely |
| D3 | Embedding provider default | M2 | OpenAI `text-embedding-3-small`; local `bge-small-en-v1.5` in vLLM | Ship both adapters; default to OpenAI for cloud, local for airgap — one env var flips it |
| D4 | Default `LLM_MODEL_DEEP` | M3 | Claude Sonnet 4.6 (excellent for reasoning); GPT-4o; Llama 3.1 70B via vLLM | Claude Sonnet 4.6. Users override in one config line |
| D5 | Rate limiter | M1 | Postgres token bucket; Redis (SlowAPI); nothing (rely on forge webhooks being polite) | Nothing in M1. Add Redis-backed limiter in M3 when the API is public |
| D6 | Web hosting for the compose target | M0 | `nginx` in a `web` container; ship as part of the `api` image | Separate `web` container — matches the S3/SWA topology and keeps the image lean |
| D7 | Vector store | M2 | pgvector (as PRD); Qdrant sidecar | pgvector. One datastore is the correct answer until it isn't |
| D8 | Prompt cache backend | M3 | Redis; filesystem; off | Redis when available, filesystem otherwise. Cache lives outside the model provider so switching providers keeps hits |
| D9 | Airgap egress allowlist mechanism | M6 | container-level `iptables`; app-level allowlist middleware; both | Both. App-level middleware fails-closed on any HTTP client instantiation whose host is not on the allowlist |
| D10 | Multi-org vs single-org in v1 | M0 | Force single org; support multi from day one | Multi (schema already has `org_id` everywhere) but ship a single seeded org; UI hides the org switcher |
| D11 | Second-approver mechanism | M3 | Second `/crv bypass approve` comment from a different authorized user; a signed approval via API | Second comment. Zero new UI |
| D12 | Cost of a "run" surfaced where | M4 | Only in the run detail page; also in the PR summary comment | Both. Cost visibility is what stops runaway spend |
| D13 | SCIP indexer packaging | M6 | Bake all SCIP toolchains into `indexer.Dockerfile` (~2 GB); pull on demand | Bake — pulling at runtime is slow and airgap-hostile |

---

## Part C — Deployment Guides

### C1. Docker Compose (laptop + on-prem VM)

**Target:** developer laptops, evaluator sandboxes, small on-prem VMs (2–4 vCPU, 8 GB RAM).

**Files:**
```
deploy/compose/
  docker-compose.yml            # the default topology
  docker-compose.airgap.yml     # override: no LiteLLM, expects LLM_BASE_URL to be reachable
  .env.example                  # every env var from §14 layer 1
```

**Bring-up:**
```bash
git clone https://github.com/<org>/sentry-review && cd sentry-review
cp deploy/compose/.env.example .env
# edit .env: at minimum, LLM_BASE_URL and LLM_API_KEY_REF (or point at Ollama)
crv init            # optional: wizard writes .env for you
docker compose --project-directory deploy/compose up -d
crv doctor          # verifies db, queue, storage, forge, LLM
```

**Compose services:**

| Service | Image | Notes |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | volume `pgdata`; runs `migrations/alembic upgrade head` via `depends_on` init container |
| `redis` | `redis:7-alpine` | queue + prompt cache; `--maxmemory 512mb --maxmemory-policy allkeys-lru` |
| `api` | `crv-api:$VERSION` | ports 8080; env-file `.env`; `depends_on: [postgres, redis]` |
| `worker` | `crv-worker:$VERSION` | scale via `docker compose up -d --scale worker=3` |
| `web` | `crv-web:$VERSION` | serves static export via `nginx`, port 3000; `entrypoint` writes `config.js` from env before starting nginx |
| `litellm` | `ghcr.io/berriai/litellm:main-stable` | optional; only if you want a proxy in front of hosted models |

**Sizing:**
- **Laptop dev:** default resources — everything on one machine.
- **On-prem 2-vCPU / 8 GB VM:** 1× worker replica; `INDEXER_MAX_MEMORY_MB=1024`; expect baselines on 500k-LOC repos to take ~2× the reference time. Fine for 5–10 repos.
- **On-prem 8-vCPU / 32 GB VM:** 4× worker replicas; comfortable up to ~50 repos.

**Backup:** `pg_dump` on cron + rsync of the object-store volume. If losing findings history is acceptable, only the `bypasses` and `audit_log` tables need to be backed up.

**Upgrade:** `docker compose pull && docker compose up -d`. Alembic migrations run automatically on API boot behind an advisory lock — safe with multiple API replicas.

### C2. AWS: Lambda + ECS Fargate + S3

**Target:** teams already on AWS wanting managed everything.

**Topology:**
```
Forges → API Gateway HTTP API → Lambda (crv-api image)
                                    │
                                    ▼
                              SQS Standard queue
                                    │
                        ┌───────────┴─────────────┐
                        ▼                         ▼
              Lambda (short jobs, <15m)   ECS Fargate service (long jobs)
                                                  │
                                                  ▼
                                          RDS Postgres 16 (pgvector) + S3
                                                  │
                                                  ▼
                                        AWS Secrets Manager
                                                  │
                                                  ▼
                                        Web → S3 + CloudFront (OAC)
                                                  │
                                                  ▼
                              LLM: Bedrock, or external endpoint via LiteLLM on Fargate
```

**Terraform module:** `deploy/terraform/modules/aws/`

- `variables.tf` — `stack_name`, `db_instance_class`, `worker_task_count`, `use_bedrock`
- `main.tf` — VPC (single-AZ for dev, 3-AZ for prod), RDS, S3 (private, versioned), CloudFront + OAC, SQS + DLQ, Lambda + API Gateway, ECS cluster + service, IAM roles with least-privilege policies
- `outputs.tf` — `api_url`, `web_url`, `db_endpoint`

The `crv deploy --target aws` command wraps this module — but the module is usable directly with `terraform apply` for shops with existing pipelines.

**IAM boundaries:** the Lambda's role can `sqs:SendMessage` and `secretsmanager:GetSecretValue` for the allowlisted secret ARNs — nothing else. The ECS task role can additionally `s3:*Object` on the analysis bucket and read from Secrets Manager. No `*:*` policies anywhere.

**Cold-start:** the API Lambda uses a container image (not Zip). Cold-start is ~1.5 s the first request, ~200 ms warm. Webhook signature verification happens *before* any cold-start-worsening work, so the 500ms SLA holds warm and misses cold — which is acceptable per PRD §5 (webhooks are async anyway).

**Config injection at deploy time:**
1. Terraform outputs `api_url`.
2. `crv deploy` runs `next build && next export`, then writes `web/out/config.js` with `window.__CRV_CONFIG__ = { apiBaseUrl: "<api_url>" }`.
3. `aws s3 sync web/out/ s3://<bucket>/ --cache-control "public, max-age=60"` for `config.js`, longer for hashed assets.
4. CloudFront invalidation on `/config.js` and `/index.html`.

### C3. Azure: Container Apps + Static Web Apps + Service Bus

**Target:** teams on Azure. Same containers, same code, different bindings.

**Topology:**
```
Forges → Container Apps Ingress → crv-api Container App (min 1, max N)
                                        │
                                        ▼
                                Service Bus queue
                                        │
                                        ▼
                        Container Apps Job (crv-worker), KEDA scale on Service Bus depth
                                        │
                                        ▼
                        Azure DB for PostgreSQL Flexible + Blob Storage
                                        │
                                        ▼
                                    Key Vault
                                        │
                                        ▼
                                Web → Static Web Apps
                                        │
                                        ▼
                    LLM: Azure OpenAI, or external endpoint via LiteLLM on Container Apps
```

**Terraform module:** `deploy/terraform/modules/azure/`

- Provider-agnostic subset of variables (`stack_name`, `location`, `db_sku`, `worker_min_replicas`, `worker_max_replicas`)
- Managed identities everywhere; no service principals with static credentials
- Container Apps environment is single log-analytics workspace to keep telemetry stitched

**KEDA scaler:** Container Apps' built-in Service Bus scaler at `messageCount: 5` per replica. Cold-start is real (~30–60 s) but only affects the first message after idle — production usage never idles this long.

**Web on Static Web Apps:** SWA supports Next.js static export directly. `staticwebapp.config.json` sets `navigationFallback` to `/index.html` and injects `config.js` via the SWA "Application Settings" that are exposed to the client. Or (simpler, our recommendation): write `config.js` before `swa deploy`, exactly as with S3.

### C4. Kubernetes Helm chart (cloud-agnostic + airgap)

**Target:** existing k8s shops; airgapped environments; multi-cloud.

**Chart:** `deploy/helm/codereview/`

```
Chart.yaml            # crv, appVersion tracks the image tag
values.yaml           # every knob, sensible defaults
values.airgap.yaml    # overrides: registry rewrites, no external images pulled
templates/
  api.deployment.yaml
  api.service.yaml
  api.ingress.yaml
  api.hpa.yaml
  worker.deployment.yaml
  worker.hpa.yaml               # via KEDA if installed; falls back to CPU-based
  keda-scaledobject.yaml        # only rendered if .Values.keda.enabled
  postgres.deployment.yaml      # optional; skip if .Values.postgres.external
  redis.deployment.yaml         # optional; skip if .Values.queue.external
  litellm.deployment.yaml       # optional
  web.deployment.yaml
  web.service.yaml
  web.ingress.yaml
  migrations.job.yaml           # runs alembic on install/upgrade
  secrets.yaml                  # only if not using external-secrets-operator
  network-policy.yaml           # denies egress to internet in airgap mode
  service-account.yaml
  configmap.yaml                # writes web config.js
```

**Install:**
```bash
helm install crv deploy/helm/codereview \
  --namespace crv --create-namespace \
  --set image.tag=1.0.0 \
  --set postgres.external.dsn="postgresql://..." \
  --set llm.baseUrl="https://api.openai.com/v1" \
  --set-string llm.apiKey="$OPENAI_API_KEY"
```

**Airgap install:**
```bash
crv airgap package --version 1.0.0 --out crv-1.0.0-airgap.tar.gz
# copy to airgapped network
crv airgap install crv-1.0.0-airgap.tar.gz --registry registry.internal:5000
```

The `airgap package` step downloads every image (`crv-api`, `crv-worker`, `crv-indexer`, `crv-web`, `pgvector/pgvector:pg16`, `redis:7`, `litellm`, plus SCIP toolchain images), re-tags them under the internal registry, generates a `values.airgap.yaml` with the rewrites, and bundles it with the chart.

**Multi-cloud correctness:** the same chart runs on EKS/AKS/GKE/OpenShift/k3s. Storage class is a `values.yaml` knob. Ingress class ditto. External Postgres (Aurora, Cloud SQL, Flexible Server) is the recommended production path; the bundled `postgres.deployment.yaml` is for evaluation.

### C5. The `crv` single-command flow

**Scope of the CLI, deliberately narrow.** `crv` is a **deployment helper**, not a runtime admin tool. It exists to get the platform up on a target and to run in CI. It does **not** manage repos, LLMs, rules, thresholds, or reports — those live in the Web UI (PRD F9). This split is intentional:

- **CLI (`crv`) — Priya only, at install/upgrade time and in CI:**
  - `crv init` — one-time interactive/non-interactive bootstrap (target choice, forge type, LLM endpoint URL only)
  - `crv deploy` — provision infra & bring up the stack
  - `crv destroy` — inverse of deploy
  - `crv doctor` — probe health of DB/queue/storage/LLM/forge
  - `crv gate check --pr <n>` — CI-side gate probe for GitLab-non-Ultimate (returns exit code, nothing else)
  - `crv airgap package|install` — bundle images for airgapped installs
  - `crv version`
- **UI — Dana, Tom, Priya, Sam do everything else:**
  - Connect forges, add/remove repos, view live run logs
  - Configure LLM endpoints, model roles, monthly budget
  - Enable/disable rule packs, write custom rules with live-test-against-file
  - Set gate severity, min confidence, block categories, comment cap, bypass roles, second-approver policy
  - View findings, dismiss, bulk-manage, export
  - View weekly reports, spend, audit log, bypass log
  - Manage users, roles, invites

There is no `crv add-repo`, no `crv set-model`, no `crv config set gate_block_severity high`. If you want it, open the UI. The CLI never edits per-repo config, never talks to the forge on a user's behalf, never touches findings.

Priya's whole install experience is two commands.

```bash
crv init
crv deploy
```

**`crv init`** (interactive TUI by default, `--non-interactive` for CI):

1. Detects the environment (Docker present? AWS creds? Azure creds? kubeconfig?) and offers targets in order of "already usable".
2. Asks: forge type + base URL, admin email, LLM provider (or "start a local Ollama container for me").
3. Writes `.env` (compose) or `crv.config.yaml` (cloud/k8s targets).
4. Fetches or generates: forge OAuth app credentials or GitHub App private key, LLM API key handling. Never echoes secrets to stdout; writes them straight to the chosen `SecretsAdapter`.
5. Prints the exact `crv deploy` command it will run.

**`crv deploy`** (dispatches by target):

- `--target compose` → `docker compose --project-directory deploy/compose up -d` with `.env` from cwd, then `crv doctor`.
- `--target aws` → `terraform init && terraform apply -auto-approve` on `deploy/terraform/modules/aws/` with variables from `crv.config.yaml`; then upload web static export; then `crv doctor` against the API URL.
- `--target azure` → same shape, Azure module.
- `--target k8s` → `helm upgrade --install crv deploy/helm/codereview -f values-generated.yaml`.

**Credentials come from, in order of precedence:**
1. Flags (`--llm-api-key`, `--forge-token`) — highest, for CI.
2. Env vars (`CRV_LLM_API_KEY`, ...).
3. `.env` in cwd.
4. TUI prompt with masked input — only in interactive mode.

**No cred is ever written to `crv.config.yaml`.** Only refs (`llm.apiKeyRef: "openai-key"`) that resolve through the chosen SecretsAdapter.

**`crv destroy`** — inverse of deploy. Terraform destroy for cloud; `helm uninstall` + optional PVC cleanup for k8s; `docker compose down -v` for compose. Confirms with the stack name typed twice for cloud targets.

**`crv doctor`** — probes DB, queue, storage, LLM endpoint, forge auth, prints a colored status for each. Exit non-zero if any hard dependency fails.

**`crv gate check --pr <n>`** — for GitLab non-Ultimate: called from the customer's CI job, exits 0 if the gate passes, 1 if it fails. This is the fallback path when external status checks aren't available (PRD F1 AC1.6).

---

## Part D — Cost Model (per-SKU)

Prices in USD, list price, `us-east-1` / `eastus`, effective early 2026. **Prices drift.** Treat as ± 20%. All estimates assume the workload profile in §D1.

### D1. Sizing tiers

| Tier | Repos | PRs/mo | Baseline reindex/mo | LOC scanned/mo | Assumed |
|---|---:|---:|---:|---:|---|
| **XS — solo/eval** | 1–3 | 20 | 3 | 300k | 1 dev, occasional pushes |
| **S — team** | 5–15 | 150 | 20 | 3M | small team, active development |
| **M — org** | 20–50 | 500 | 60 | 15M | mid-size engineering org |
| **L — enterprise** | 100–300 | 3000 | 300 | 100M | large org, many teams |

The cost tables below quote the **M tier** as the reference. Multiply by rough factor 0.1× (XS), 0.3× (S), 6× (L) for other tiers.

### D2. AWS line items (M tier)

| Component | SKU | Unit price | Qty/mo | Cost/mo |
|---|---|---:|---:|---:|
| **API compute** | Lambda (arm64) | $0.0000133334 / GB-s | 4 GB × 500 PR × 3 s + 4 GB × 3M webhook × 0.2 s | $6 |
| API requests | Lambda invocations | $0.20 / 1M | ~600k | $0.12 |
| API gateway | HTTP API | $1.00 / 1M | ~600k | $0.60 |
| **Worker compute** | ECS Fargate | vCPU $0.04048/h, RAM $0.004445/GB-h | 2 vCPU × 4 GB × 200 h/mo average | $20 |
| Fargate — baseline reindex bursts | ECS Fargate | as above | 4 vCPU × 16 GB × 60 baselines × 0.75 h ≈ 180 vCPU-h + 720 GB-h | $10 |
| **Queue** | SQS Standard | $0.40 / 1M req | ~2M | $0.80 |
| **Database** | RDS Postgres 16, `db.t4g.medium` Multi-AZ | $0.145/h × 2 × 730 | 1 | $212 |
| DB storage | RDS gp3 | $0.115/GB-mo | 100 GB | $11.50 |
| DB backups | included up to 100% of provisioned | — | — | $0 |
| **Object store** | S3 Standard | $0.023/GB-mo | 50 GB | $1.15 |
| S3 requests | PUT/GET | $0.005 + $0.0004 / 1k | 500k PUT + 5M GET | $4.50 |
| **CloudFront** | egress | $0.085/GB (first 10 TB) | 20 GB | $1.70 |
| CloudFront requests | HTTPS | $0.01 / 10k | 500k | $0.50 |
| **Secrets Manager** | secret | $0.40 / secret-mo | 8 | $3.20 |
| Secrets Manager | GET | $0.05 / 10k | 100k | $0.50 |
| **CloudWatch Logs** | ingestion | $0.50/GB | 20 GB | $10 |
| CloudWatch Metrics | custom metrics | $0.30/metric-mo | 20 | $6 |
| **VPC** | NAT Gateway | $0.045/h + $0.045/GB | 730 h + 30 GB | $34 |
| **Data transfer** | inter-AZ | $0.01/GB | 30 GB | $0.30 |
| **Total AWS infra (M tier)** | | | | **≈ $322/mo** |

Notes:
- Multi-AZ RDS is half the total. A single-AZ `db.t4g.small` for dev drops the total to ~$130/mo.
- If you skip CloudFront and serve web from S3 with a `*.s3-website` URL, subtract $2.20 but lose HTTPS on a custom domain. Not worth it in production.
- Bedrock LLM traffic is priced in [§D5](#d5-llm-operating-cost).

### D3. Azure line items (M tier)

| Component | SKU | Unit price | Qty/mo | Cost/mo |
|---|---|---:|---:|---:|
| **API compute** | Container Apps (Consumption) | vCPU $0.000024/s active + $0.000003/s idle; RAM $0.0000025/GB-s | 0.5 vCPU × 1 GB × 730 h idle + spikes | $20 |
| **Worker compute** | Container Apps (Consumption) | as above | 1 vCPU × 2 GB × 200 h active + 4 vCPU × 8 GB × 45 h baseline | $65 |
| **Queue** | Service Bus Standard | $9.81 base + $0.05/1M | 1 namespace, 2M | $10 |
| **Database** | Azure DB for PostgreSQL Flexible, `B2ms` (2 vCPU, 8 GB) zone-redundant HA | $0.234/h × 2 × 730 | 1 | $342 |
| DB storage | Flexible P10 (128 GB) | $0.115/GB-mo | 128 GB | $14.72 |
| DB backups | first 100% free | — | — | $0 |
| **Blob Storage** | Hot LRS | $0.021/GB-mo | 50 GB | $1.05 |
| Blob transactions | writes $0.065 / 10k; reads $0.005 / 10k | 500k write + 5M read | | $5.75 |
| **Static Web Apps** | Standard | $9/mo per app | 1 | $9 |
| **Key Vault** | secret ops | $0.03 / 10k ops | 200k | $0.60 |
| **Log Analytics** | ingestion | $2.30/GB (first 5 GB free) | 20 GB | $34.50 |
| **Application Insights** | included in Log Analytics | | | |
| **Networking** | Container Apps public egress | $0.087/GB | 30 GB | $2.61 |
| **Total Azure infra (M tier)** | | | | **≈ $505/mo** |

Notes:
- Azure PostgreSQL is the biggest single line and the least flexible. Dropping to a Burstable `B1ms` non-HA cuts $250 off but is dev-grade only.
- Container Apps' idle-vCPU pricing means always-on API replicas cost more than Lambda for low-traffic deployments. Above ~2M requests/mo the delta shrinks.
- Log Analytics ingestion is the second-largest surprise. Set retention to 30 days; keep debug logs sampled.

### D4. On-prem / self-hosted

The scenario the PRD centers on. Two shapes.

**On-prem, small VM (S tier):**

| Component | Provisioning | Approx cost |
|---|---|---:|
| 1× VM: 4 vCPU, 16 GB RAM, 200 GB SSD | Existing internal cluster, or ~$40/mo on Hetzner CX41 | $0–40 |
| Backup snapshot bucket | 20 GB | $0–5 |
| **Infra total** | | **$0–45/mo** |

Everything runs under compose on the one VM. Postgres, Redis, API, worker, web, optionally LiteLLM. This is the recommended shape for evaluation and for teams up to ~15 developers.

**On-prem, HA cluster (M tier, self-managed k8s):**

| Component | Shape | Notes |
|---|---|---|
| 3-node control plane + 6-node worker k3s cluster | Existing hardware | Runs the Helm chart |
| External Postgres 16 (patroni or existing DBA-managed) | 4 vCPU, 16 GB, 500 GB, HA | |
| MinIO for object store | 3-node distributed | Or existing S3-compatible |
| External LLM endpoint or local vLLM cluster | 1× GPU node (A100 40GB or L40S) for local models | GPU cost dominates if used |

Infrastructure cost is a function of existing hardware. If everything is already provisioned, the incremental cost is `$0 + LLM`.

### D5. LLM operating cost

Model prices, per 1M tokens (early 2026, list):

| Model | Input $ | Output $ | Used for |
|---|---:|---:|---|
| Claude Sonnet 4.6 | $3.00 | $15.00 | `LLM_MODEL_DEEP` default |
| Claude Haiku 4.5 | $1.00 | $5.00 | `LLM_MODEL_FAST` option |
| GPT-4o | $2.50 | $10.00 | `LLM_MODEL_DEEP` alt |
| GPT-4o mini | $0.15 | $0.60 | `LLM_MODEL_FAST` default |
| Bedrock Claude Sonnet 4.6 | $3.00 | $15.00 | AWS-native |
| Azure OpenAI GPT-4o | $2.50 | $10.00 | Azure-native |
| Llama 3.1 70B (vLLM, GPU) | $0 tokens (GPU cost only) | | Airgap/local |
| `text-embedding-3-small` | $0.02 / 1M | | embeddings |

**Cost per PR review (typical):**

Assumes an average PR touching 4 files, 200 lines changed, with 3 relevant callers pulled into the context pack.

| Path | Fast tokens (in/out) | Deep tokens (in/out) | Cost |
|---|---:|---:|---:|
| Fast triage only (small PR, no security signal) | 8k / 1k | 0 / 0 | $0.0018 (GPT-4o mini) or $0.014 (Haiku) |
| Full review (default) | 8k / 1k | 25k / 3k | $0.12 (mini + Sonnet) or $0.16 (mini + GPT-4o) |
| Large PR, high blast radius | 12k / 2k | 60k / 6k | $0.27 |

With **prompt cache at 30% hit rate** (AC8.4 requirement) the effective cost is ~30% lower.

**Monthly LLM cost by tier** (Claude Sonnet 4.6 deep, GPT-4o mini fast, 30% cache):

| Tier | PRs/mo | Baseline hotspots | Weekly drift | Cost/mo |
|---|---:|---:|---:|---:|
| XS | 20 | 3 × 150 = 450 file reviews (~$0.03 each) | 4 | ~$15 |
| S | 150 | 20 × 150 = 3000 | 20 | ~$80 |
| M | 500 | 60 × 150 = 9000 | 50 | ~$220 |
| L | 3000 | 300 × 150 = 45000 | 300 | ~$1400 |

**Airgap / local model cost:** dominated by GPU. One L40S (48 GB) on-prem runs Llama 3.1 70B AWQ at ~4 tokens/s single-stream, ~40 tokens/s batched — enough for the M tier if the workload is time-sharable. Cloud GPU rental (Lambda Labs, RunPod) is ~$0.80/h for L40S ≈ $580/mo continuous. On-prem amortized ≈ $200/mo over 3 years for the GPU itself.

### D6. What drives cost up and how to stop it

Ranked by impact.

| Driver | Impact | Mitigation |
|---|---|---|
| **Uncapped baselines** on huge repos | 10× LLM bill if a 5M-LOC monorepo gets a hotspot budget bug | `BASELINE_MAX_COST_USD` is a hard cap in the orchestrator (AC4.2). Enforced *before* spending, not after. |
| **Prompt cache off** or low hit rate | 30–50% higher LLM cost | Turn on `PROMPT_CACHE_BACKEND`. Monitor `crv_llm_cache_hits_total / crv_llm_calls_total`. If <20%, investigate — usually stale-cache eviction. |
| **Multi-AZ RDS or Azure HA Postgres** in non-prod | ~$200/mo per env | Single-AZ for dev/staging. Only prod is Multi-AZ. |
| **Log ingestion** (CloudWatch, Log Analytics) | $30–100/mo surprise | Set `LOG_LEVEL=info`. Sample debug logs. 30-day retention max. |
| **NAT Gateway** on AWS | $34/mo flat + egress | Put workers in a VPC endpoint-heavy subnet if the LLM is Bedrock. External LLM endpoints still need NAT unless you use PrivateLink. |
| **Long-lived idle workers** | 2–3× compute over event-driven | Prefer KEDA/Container Apps scale-to-zero. Compose target keeps `worker` alive because there's no cold-start cost locally. |
| **Blast-radius depth = 3** | 4× the LLM tokens vs depth 2 | Ship default = 2. Only bump for a specific critical path via `.crv.yml`. |
| **`MAX_COMMENTS_PER_PR` too high** | Reviewer fatigue → tool ignored → wasted $ | Default 25 is already generous. |

---

## Part E — Container Strategy

**Four images, one Dockerfile per image, no `docker-compose.dev.yml` sprawl.**

| Image | Base | Contents | Approx size |
|---|---|---|---:|
| `crv-api` | `python:3.12-slim` | wheels for `apps/api` + `packages/{core,adapters,rules}`. No build toolchains. | ~200 MB |
| `crv-worker` | `python:3.12-slim` | same wheels + `apps/worker`. Adds `git`, tree-sitter grammars via wheels. | ~350 MB |
| `crv-indexer` | `python:3.12` (fat) | worker image + JDK 21 + Node 20 + Go 1.23 + Cargo + SCIP CLIs. Used only when the orchestrator picks the "heavy" runner tier. | ~1.8 GB |
| `crv-web` | `nginx:alpine` | static export from `apps/web` + entrypoint script that renders `/usr/share/nginx/html/config.js` from env at container start | ~40 MB |

**Rules that keep images clean:**

1. **One process per image.** No `supervisord`, no `entrypoint.sh` that starts three things.
2. **Non-root by default.** `USER 10001:10001`. Compose bind mounts owned by that uid.
3. **Multi-stage builds.** Wheel building in a builder stage, runtime image starts from `slim`. No compilers in production images.
4. **No latest tags anywhere.** CI stamps `crv-*:<git-sha>` and `crv-*:<semver>`.
5. **Signed and SBOM'd** (M6): `cosign sign` on push, `syft` for SBOM, `grype` in CI on every PR to the tool itself.

**When `crv-indexer` runs:** the orchestrator picks it when `JobSpec.language ∈ Tier-1 AND scip_enabled`. Everything else uses `crv-worker`. This keeps the average cold-start fast while still supporting precise xrefs.

---

## Part F — Risk Register

Ranked by "what would kill the project".

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | LLM output is noisy → teams disable the tool → adoption dies | High | Fatal | Aggressive filtering (F5 stage 8), `MIN_CONFIDENCE` default 0.6, `MAX_COMMENTS_PER_PR` default 25, dismissal-fingerprint memory. Measure `% findings marked not-useful`; alarm at >15%. |
| **R2** | Blast-radius quality on Tier-2 languages is bad (heuristic xrefs miss cross-file uses) | Medium | Medium | Ship SCIP for Tier-1 first. On Tier-2, be explicit in the comment: "heuristic reference — verify manually." Do not silently under-detect. |
| **R3** | GitLab non-Ultimate customers can't block merges | High for that segment | Medium | Fallback CI-job path (F1 AC1.6, `crv gate check`) documented, tested end-to-end in M4. |
| **R4** | LLM provider outage during a deployment window | Medium | Medium | `GATE_MODE=fail_open` by default. Deterministic scanners still run. `neutral` status. |
| **R5** | Postgres becomes the bottleneck for the symbol graph on huge monorepos | Medium | Medium | Sharding by `repo_id` is trivial (all indexes already lead with it). Add read replicas for the UI queries first. |
| **R6** | Vendor lock-in creeping in via convenient shortcuts | Medium | Fatal to the whole thesis | Import-linter contract from M0. **Non-negotiable.** A PR that violates it fails CI, period. |
| **R7** | Airgap validation is theoretical, not tested | Medium | High for regulated customers | M6 has an airgap CI job that runs the whole suite with outbound blocked. Any test that fails there → real defect. |
| **R8** | Cost overrun on a customer's first baseline | Medium | High for that customer | `BASELINE_MAX_COST_USD` enforced before spending. Baseline degrades to fewer hotspots rather than exceeding budget (AC4.2). |
| **R9** | Bypass abuse (a maintainer bypasses everything) | Low | Medium | Audit log is append-only, exported yearly. Weekly report includes bypass count per actor. Framed as visibility, not policing. |
| **R10** | The tool itself becomes over-engineered | Medium | Medium | Ponytail active on all internal work. Import-linter, no-abstraction-until-two-users rule. |

---

*End of plan.md — kept short where it could be, long where the user asked for detail (per-SKU costs, missing PRD sections). Read alongside PRD.md; neither is complete without the other.*
