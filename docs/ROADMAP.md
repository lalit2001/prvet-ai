# PRVet Maturity Roadmap

Where the product is, where it needs to be, and the order to get there. Companion to
[`PRD.md`](../PRD.md) (the what) and [`ARCHITECTURE.md`](ARCHITECTURE.md) (the shape).

---

## 0. Honest state (2026-09) — updated 2026-09-27: M-A, M-B, M-C (GitHub) and D1/D3/D4 shipped; table below describes the state before that work

| Capability | README says | Code does |
|---|---|---|
| Symbol index | tree-sitter + SCIP graph | `files` + `symbols` written by `baseline.py`. Python via stdlib `ast`, JS/TS via tree-sitter. Definitions only. |
| Cross-file linkage | "analyzes caller usages across the entire codebase" | `symbol_references` table exists in DDL, **never written**. No import or call-site extraction. |
| Blast radius | core promise (PRD G2) | `context/__init__.py` is a one-line docstring. `pr_review.py` reviews each diff hunk in isolation and prints "blast radius coming soon" in the PR comment. |
| AST Viewer | bidirectional code ↔ AST highlighting | Works, but renders a single file's raw parse tree. Cannot show linkage because a parse tree has none. |
| Forge install | GitHub / GitLab / Azure | PAT pasted into UI, stored as `capabilities.dev_token` JSONB. One connection = one human's token. Webhooks registered per repo. |
| SAST | Semgrep pre-filter | `packages/rules/semgrep` exists; not wired into the PR job. |
| Gate | `prvet gate check` | Reads findings; no `gate_decisions` written by the review job. |
| Embeddings | pgvector chunks | Table exists, nothing writes or reads it. |

The gap is not the viewer. The gap is that the **graph is never built**, so nothing downstream
(review context, viewer, hotspots, gate) has anything to link.

---

## 1. Target architecture

```
                 ┌──────────── forge (GitHub App / GitLab / AzDO) ────────────┐
   webhook ─────►│ api: verify, dedupe, enqueue                               │
                 └───────────────┬───────────────────────────────────────────┘
                                 ▼
            worker: jobs/index.py  (checkout head SHA → incremental index)
                     │  walk → parse → FileFacts{symbols, imports, refs}
                     │  resolve imports → files ; refs → symbols
                     │  upsert symbols + symbol_references (per file, txn)
                     ▼
            worker: context/   blast_radius(changed) → packer(budget) → prompt
                     ▼
            worker: analysis/  semgrep pre-filter ─► fast triage ─► deep review
                     │          dedupe by fingerprint, filter to diff ∪ blast ∪ security
                     ▼
            forge:  check-run + batched review + blast-radius table
            db:     findings(affected_symbols), gate_decisions, llm_calls(cost)
            ui:     PR page, Symbol Explorer, run timeline
```

One `Extractor` contract per language producing `FileFacts`. One resolver. No SCIP/LSP until
heuristic resolution is measured and found short.

---

## 2. Track A — Code graph & blast radius

### A0. Foundation (1 day)
- Fix `pr_review.py`: full-file fetch uses the httpx client after its `async with` closed → every fetch fails silently.
- `indexing/pyast.py`: add `ExtractedImport(module, name, alias, line)`, `ExtractedRef(name, line, kind)` where `kind ∈ {call, attr, inherit, decorator, type, import}`. Return `FileFacts(symbols, imports, refs)` from every extractor so `persist.py` stays parser-agnostic.
- `apps/worker/tests/fixtures/{py,ts}/` golden files → expected `FileFacts`. One test per language. This is the check that keeps the graph honest as parsers evolve.

### A1. Reference extraction (2–3 days)
**Python** — walk `ast.Call` (`Name`/`Attribute` callee), `Attribute` chains, `ClassDef.bases`, decorators, annotations. `Import`/`ImportFrom` → absolute module via `importlib.util.resolve_name` + `module_key_for`.

**JS/TS** — switch from hand-walking to tree-sitter **queries** (`indexing/queries/{javascript,typescript,tsx}.scm`):
- `import_statement` → specifier + default/named/namespace bindings
- `call_expression`, `new_expression`, `extends_clause`, `type_identifier`
- `export_statement` re-exports

Resolve relative specifiers (`./foo` → `foo.ts|tsx|js|/index.*`); read `tsconfig.json` `baseUrl`/`paths` once per repo.

### A2. Resolution + persistence (2 days)
`indexing/resolve.py`:
1. Pass 1: files + symbols (exists).
2. Pass 2: per file, scope = local symbols → imported bindings (import → target file → symbols by name) → same-package fallback. Emit `symbol_references` with `precision ∈ {heuristic, import-resolved}`.
3. `persist.replace_references(db, file_id, refs)` mirroring `replace_symbols`.

Record `unresolved_count` per file; expose **resolution rate** in run stats. PRD target: ≥90% of changed public symbols have reverse refs.

### A3. Incremental indexing (1–2 days)
- Skip files with unchanged `content_hash`.
- Re-resolve only changed files ∪ files that import them.
- `jobs/index.py` becomes the single "index tree at SHA" entry point; `baseline.py` and `pr_review.py` both call it.
- PR review checks out head SHA via `git fetch` + `git worktree add` under a temp dir; cleanup in `finally`.

### A4. Blast radius → review context (2 days)
- `context/blast_radius.py`: BFS on `to_symbol_id → from_symbol_id`, depth 2, cap 40, score +2 public caller, +2 signature changed (compare `symbols.signature` base vs head).
- `context/packer.py`: `[changed symbol] + ranked callers` under a token budget (chars/4 until real token accounting exists).
- `pr_review.py`: hunks → symbols by line range → one review call per changed symbol group with a `Callers:` section. Fill `findings.affected_symbols`. Summary gains a blast-radius table. Keep off-diff findings only when `category=security` or they cite a blast-radius symbol (PRD §765).

### A5. Languages & precision (ongoing)
- Go, Java via `.scm` queries — one file + ~50-line resolver each.
- `symbols.fan_in/fan_out` at index time; hotspot ranking = fan-in × churn (`git log --numstat`) instead of LOC.
- SCIP overlay (`scip-python`, `scip-typescript`) with `precision='scip'` **only** after heuristic rate is measured on a real repo and falls short.

---

## 3. Track B — UI

### B1. Symbol Explorer (replaces AST Viewer as default; raw AST stays as a "Debug: parse tree" tab)
Route: `/admin/ast` → rename `/explorer`, open to members (read-only), not admin-only.

Layout: file tree │ code pane │ inspector.
- **Outline**: symbols in file (kind, visibility, lines) — `GET /repos/{id}/files/{path}/symbols`.
- **Inspector** for selected symbol: Definition · Callers · Callees · Importers — `GET /symbols/{id}/refs?dir=in|out`. Every row click → file + line in code pane.
- **File linkage panel**: imports / imported-by for the current file.
- **Blast-radius preview**: `GET /symbols/{id}/blast?depth=2` → ranked list + small force graph (`d3-force`, lists first, graph second). This is the demo feature and the debugger for A4.
- Search box: fuzzy symbol search across repo (`ILIKE` on `symbols.name`, indexed) — px0-style instant navigation.

### B2. PR review page (`/prs/[id]`)
- Header: risk score, severity counts, cost, duration, model roles used.
- **Blast-radius table**: changed symbol → callers affected (depth, file, line) → findings referencing them.
- Diff viewer with findings anchored inline; toggle "show callers" expands referenced call-sites beside the hunk.
- Per-finding actions: dismiss (false positive), snooze, "explain more" (`@prvet` reply reuses `jobs/pr_reply.py`), apply suggested patch (opens forge suggestion).
- Re-review button (enqueue with `force`).

### B3. Run observability (`/runs/[id]`)
Timeline of phases (checkout → index → semgrep → triage → deep → post) with durations, files/s, symbols, refs, **resolution %**, token usage & cost per phase from `llm_calls`. Failures show the stage and the error, not a stack trace dump.

### B4. Repo health (`/repo/[id]`)
- Baseline metrics over time (findings by severity, fan-in hotspots, resolution rate).
- Hotspot list (fan-in × churn) linking into Explorer.
- Weekly drift: findings delta vs previous baseline.
- Repo settings: languages, excluded paths (`.crvignore` + UI), review depth, gate thresholds, cost cap.

### B5. Org / admin
- Installations page (Track C): connected apps, repos enabled, webhook health (last delivery, failures).
- Providers: model roles fast/deep with per-role cost estimate.
- Audit log already exists — add filters and export.

---

## 4. Track C — Install as an app (GitHub App, GitLab, Azure DevOps)

Goal: after `docker compose up` / Helm deploy, an admin clicks **Install on GitHub**, picks repos, done. No PATs, no per-repo webhook setup, works for orgs and personal accounts.

### C1. Data model
```sql
CREATE TABLE forge_apps (            -- one row per registered app per deployment
  id UUID PK, org_id UUID, forge_type TEXT, base_url TEXT,
  app_id TEXT, client_id TEXT, slug TEXT,
  private_key_ref TEXT, client_secret_ref TEXT, webhook_secret_ref TEXT,
  created_at TIMESTAMPTZ
);
CREATE TABLE forge_installations (   -- one row per install (org/user) of an app
  id UUID PK, app_id UUID REFERENCES forge_apps, installation_id TEXT,
  account_login TEXT, account_type TEXT, repo_selection TEXT,
  suspended_at TIMESTAMPTZ, created_at TIMESTAMPTZ,
  UNIQUE (app_id, installation_id)
);
ALTER TABLE repositories ADD COLUMN installation_id UUID REFERENCES forge_installations;
```
`forge_connections` (PAT) stays for self-hosted GitLab/Gitea/dev; the UI labels it "Personal token (advanced)".

### C2. GitHub App
- **Registration**: use the [App Manifest flow](https://docs.github.com/apps/sharing-github-apps/registering-a-github-app-from-a-manifest) — the UI posts a manifest (name, `hook_url = {PUBLIC_URL}/webhooks/github/app`, permissions, events), GitHub redirects back with a code, API exchanges it for `app_id`, `pem`, `webhook_secret`, `client_secret`, stores refs via `SecretsAdapter`. Zero manual copy-paste.
- **Permissions**: `contents:read`, `pull_requests:write`, `checks:write`, `metadata:read`, `issues:write` (for `@prvet` replies). Events: `pull_request`, `pull_request_review_comment`, `issue_comment`, `push`, `installation`, `installation_repositories`, `check_suite` (rerequested).
- **Auth**: `packages/adapters/forge/github_app.py` — JWT (RS256, 10-min) → `POST /app/installations/{id}/access_tokens` → cached installation token (1h, refresh at 50 min). Adapter picks credential source per repo: installation token if `installation_id` else `dev_token`.
- **Webhook**: single endpoint `/webhooks/github/app` (app-level secret). `installation.created/deleted/suspend`, `installation_repositories.added/removed` keep `forge_installations` + `repositories` in sync automatically.
- **Checks API**: post a Check Run (`in_progress` → `completed` with `conclusion` from gate) instead of a commit status. Annotations carry inline findings (up to 50/req). Gate becomes a required check in branch protection — that is the professional-grade merge gate.
- **Setup URL**: after install GitHub redirects to `{PUBLIC_URL}/setup?installation_id=…` → UI shows repos, enables baseline.
- **Marketplace-readiness**: `installation` event handling, `setup_url`, `callback_url`, and OAuth "login with GitHub" (`users` gets `github_id`) so reviewers land on the PR page without a seeded password.

### C3. GitLab
- Register an **OAuth application** (or group-level access token for self-managed). Adapter: `POST /oauth/token` refresh flow; store refresh token via `SecretsAdapter`.
- Webhooks: **group-level hooks** (one hook covers all projects) with `X-Gitlab-Token`.
- Output: Merge Request discussions + **external status check** / commit status; `prvet gate` maps to pipeline status.

### C4. Azure DevOps
- Service Principal / Entra app (client-credentials) or org-level PAT as fallback.
- **Service Hooks** at project level for `git.pullrequest.created/updated`, `ms.vss-code.git-pullrequest-comment-event`.
- Output: PR threads + **PR status API** (`/statuses`) which can be made a branch policy → gate.

### C5. Multi-tenant hardening
- `PUBLIC_URL` setting required; webhook URLs derived, not typed.
- Replay protection: dedupe on `(app_id, delivery_id)` (exists per connection; extend).
- Per-installation rate limits and cost caps.
- Secrets: `dev_token` in JSONB is dev-only. `SecretsAdapter` backends: env/file (compose), AWS Secrets Manager, Azure Key Vault, K8s Secret. Migration script moves existing `dev_token` → secrets backend.

### C6. Distribution
- `prvet deploy` prints the "Install on GitHub" URL at the end.
- Helm chart values for `PUBLIC_URL`, ingress, secrets backend.
- Landing page: install button + screenshot of blast-radius table.

---

## 5. Track D — Advanced review capabilities

### D1. Two-pass review (routing by task, PRD §858)
1. **Semgrep pre-filter** (`packages/rules/semgrep`) runs on changed files → deterministic findings, `source='sast'`.
2. **Fast triage** (`LLM_MODEL_FAST`): classify each changed symbol group — trivial / needs deep / security-sensitive. Skip deep on trivial (docs, renames, tests-only).
3. **Deep review** (`LLM_MODEL_DEEP`) only on flagged groups, with blast-radius context.
Cuts cost 3–5× on typical PRs and is the difference between a toy and something you can run on every push.

### D2. Agentic deep review (tool-using LLM)
Give the deep model tools instead of a giant prompt: `read_file(path, start, end)`, `find_callers(symbol)`, `find_definition(name)`, `grep(pattern)`, `get_tests_for(symbol)`. Loop bounded by steps + token budget. The graph from Track A is what makes these tools cheap and precise. Log every tool call in `llm_calls` for the run timeline.

### D3. Finding quality
- **Stable fingerprints**: `sha(repo, file, symbol_key, category, normalized_title)` — survives line shifts. Reopen/close across runs; a finding that disappears after a push is auto-resolved.
- **Dedupe** semgrep vs LLM findings on same symbol+category; prefer SAST evidence, keep LLM explanation.
- **Confidence calibration**: track dismissal rate per category/rule; auto-lower confidence threshold display for noisy categories; surface in admin.
- **Verification pass**: for `critical/high`, a second cheap call asks "given this code, is the finding real?" — drop if not confirmed. Halves false positives.
- **Suggested patches** posted as forge suggestion blocks (one-click apply).

### D4. Risk score & gate
- Per-PR risk = f(severity counts, blast-radius size, signature changes to public symbols, security-sensitive paths touched, test coverage delta). Shown on PR page and check-run title.
- `gate_decisions` written at end of each run using repo thresholds; `prvet gate check` reads it. Bypass flow writes `bypasses` + audit.

### D5. Custom rules & policies
- Repo-level `.prvet.yml`: languages, exclude paths, severity thresholds, custom review guidelines (free-text injected into system prompt), path-scoped rules (`apps/api/** → security focus`).
- Admin UI already generates rules via LLM — persist as Semgrep rules + prompt guidelines with versioning.
- Org-wide policy inheritance.

### D6. Baseline & drift
- Baseline hotspots by fan-in × churn (A5).
- Weekly job (`jobs/weekly.py` stub): re-index default branch, diff findings vs previous baseline, post digest (forge issue / Slack webhook / email).
- Metrics: complexity (radon-style for Python, cyclomatic via tree-sitter node counts for TS), coupling (fan-in/out), dead public symbols (fan-in 0, exported).

### D7. Conversational review
`@prvet` handler exists (`jobs/pr_reply.py`). Extend with intents: `@prvet explain`, `@prvet ignore <finding>` (dismiss + learn), `@prvet review again`, `@prvet why is this in blast radius` (walks the reference path).

### D8. Cost & tokens
- Real token accounting in `llm_calls` (prompt/completion, model, USD via a pricing table in provider settings).
- Prompt caching for the stable prefix (system prompt + repo guidelines).
- Per-repo/day budget with hard stop and UI banner.

---

## 6. Track E — Platform maturity

- **Tests**: worker unit tests for extractors/resolver/blast radius (golden fixtures); API tests for webhook verification + installation lifecycle; one end-to-end test with a fixture repo and a mocked LLM.
- **CI**: lint (`ruff`, `import-linter`), type-check (`pyright` strict on `packages/`), tests, Docker build, Helm lint. Release on tag → GHCR images + CLI binaries.
- **Observability**: structlog already a dep — actually use it (replace `print`). Request IDs through webhook → job → LLM calls. Prometheus `/metrics`: jobs, durations, LLM cost, resolution rate.
- **Reliability**: job timeouts, retries with backoff, dead-letter list in UI, idempotency keys everywhere (exists for runs).
- **Security**: secrets out of JSONB (C5), webhook signature everywhere (exists), CSRF on UI, RBAC already present — add per-repo visibility.
- **Docs**: rewrite README §4A for Symbol Explorer; add `docs/INDEXING.md` (this track A in detail), `docs/INSTALL_GITHUB_APP.md`, `docs/CONFIG.md` update for `.prvet.yml`.
- **Versioned schema exports**: baseline snapshot to object store only once something consumes it.

---

## 6b. Track F — Agent-native surface (Claude Code, Gemini CLI, Cursor, Aider, …)

The graph and the reviewer should be usable from **inside any coding-agent harness**, the way px0 dispatches to agents. Two thin surfaces over the existing API — no new logic in the CLI.

**Boundary rule stays:** the `prvet` CLI is deploy-only for *configuration*. Nothing below adds repos, models, rules or thresholds; those remain UI-only. What is added is **read-only graph queries** and **triggering a review the server already knows how to run**.

### F1. MCP server — `prvet mcp` (stdio) and `GET/POST {PUBLIC_URL}/mcp` (HTTP)
Tools, all backed by Track A tables via the API:
- `symbol.search(query)` → fuzzy symbol hits
- `symbol.definition(symbol_key)` → file, lines, signature, docstring
- `symbol.callers(symbol_key, depth=1)` / `symbol.callees(symbol_key)`
- `file.imports(path)` / `file.importers(path)`
- `blast_radius(symbol_keys[], depth=2)` → ranked affected symbols + reference paths
- `review.diff(patch, paths[])` → findings JSON using the server's configured models (no keys on the client)
- `review.pr(repo, number)` → enqueue + poll → findings + blast table
- `findings.list(repo, pr?)` read-only
Auth: per-user API token minted in the UI (`/admin/users`), scoped read / review-trigger. Any MCP-capable harness (Claude Code `claude mcp add`, Gemini CLI, Cursor, Windsurf, Aider via mcp bridge) gets go-to-definition, find-callers and blast radius for free — which is exactly the context an agent lacks when editing.

### F2. Local review from a harness — `prvet review [--staged|--range A..B|--pr N] [--json|--sarif]`
- Computes the diff locally (`git diff`), posts to `review.diff`; prints findings in terminal, JSON for agents, SARIF for GitHub code scanning / IDE problem panes.
- `prvet review --watch` re-reviews on save for tight agent loops.
- Exit code mirrors gate thresholds so an agent can loop "edit → `prvet review` → fix" until clean before opening the PR.
- Zero config beyond `PRVET_URL` + `PRVET_TOKEN` (printed by `prvet deploy`; also downloadable from the UI).

### F3. Harness recipes (docs + `prvet mcp install --for claude-code|gemini|cursor`)
Writes the right MCP config snippet for the chosen harness. Docs page with the three-line setup per tool. Optional `CLAUDE.md` / `.cursorrules` snippet: "before finishing, run `prvet review --staged`".

### F4. Agent-authored PRs get the same review
PRs opened by bots are reviewed identically, but the summary flags `author: agent` and the deep pass is forced (agents produce plausible-looking cross-file breakage — blast radius is the whole point here).

Exit criterion: from a fresh Claude Code session in any indexed repo, `find callers of X` answers from PRVet, and `prvet review --staged` returns findings with callers cited.

---

## 7. Sequencing

| Milestone | Contents | Exit criterion |
|---|---|---|
| **M-A** Graph | A0 A1 A2 A4 | A real PR is reviewed with callers in context; PR comment shows a blast-radius table; resolution % ≥ 80 on this repo |
| **M-B** Explorer | B1 B3 | Click a symbol → see callers/callees/importers and blast-radius preview |
| **M-C** App | C1 C2 C5 | Fresh deploy → "Install on GitHub" → PR opened → check run posted, no PAT involved |
| **M-D** Quality | D1 D3 D4 A3 | Two-pass review, stable fingerprints, gate decision written, incremental index on every push |
| **M-E** Depth | D2 D5 D6 B2 B4 F1 F2 | Agentic deep review, `.prvet.yml`, weekly drift, full PR page |
| **M-F** Breadth | C3 C4 A5 D7 D8 E F3 F4 | GitLab/AzDO apps, Go/Java, cost accounting, CI/release |

Do M-A before anything else. Nothing in B–E has value until the graph exists.

## 8. Explicitly skipped (until a consumer exists)
- Embeddings / pgvector RAG — the graph gives better review context than similarity search.
- Snapshot archives to object store.
- SCIP/LSP precision layer — measure heuristic resolution first.
- Type inference beyond import resolution.
