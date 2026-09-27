# PRVet — `prvet`

Self-hosted AI code review that ships with your codebase, keeping your intellectual property securely within your virtual boundary.

- **What it does:** Reviews pull requests dynamically with their blast radius (analyzes caller usages across the entire codebase), tracks baseline health metrics, provides weekly drift alerts, and gates merges on critical code findings.
- **Where it runs:** Anywhere. `docker compose up` on your laptop, Terraform modules on AWS/Azure, or Helm charts on Kubernetes.
- **What LLM it uses:** Any OpenAI-compatible API endpoint (OpenAI, Anthropic, Bedrock, Azure OpenAI, vLLM, Ollama, etc.).

---

## 1. Quick Start (Local Docker Compose)

1. **Configure Environment Variables:**
   ```bash
   cp deploy/compose/.env.example .env
   # Edit .env to set your LLM_BASE_URL, LLM_API_KEY, and forge PAT connection tokens
   ```

2. **Start Backend Stack:**
   ```bash
   docker compose --project-directory deploy/compose up -d
   ```

3. **Access the Web Dashboard:**
   Open [http://localhost:3737](http://localhost:3737) in your browser.

---

## 2. Seeded Login Credentials

Two default user accounts are automatically seeded into the database at startup (passwords can be overridden by configuring `SEED_ADMIN_PASSWORD` and `SEED_USER_PASSWORD` variables in your `.env` file):

| Account Type | Email Address | Default Password | Role | UI View Permissions |
|---|---|---|---|---|
| **System Admin** | `admin@prvet.review` | `admin123` | `admin` | Full Access (Dashboards, Rules Config, Forge Settings, AST Viewer) |
| **Standard User** | `user@prvet.review` | `user123` | `member` | Restricted Access (Read-only dashboards, PR findings; Configuration menus hidden) |

---

## 3. Go CLI (`prvet`) Guide

The `prvet` command-line utility acts as a deployment companion and CI pipeline gatekeeper. It does not require Go on the local machine once compiled.

### A. Compile the Binary
To compile the `prvet` CLI binary from source:
```bash
go build -o prvet cli/main.go
```

### B. Global System Installation
Move the compiled binary to a folder in your environment's `$PATH`:
```bash
sudo mv prvet /usr/local/bin/prvet
sudo chmod +x /usr/local/bin/prvet
```

### C. Available CLI Commands
* **System Diagnostics:** Probe the status of your database, redis queue, object store, and api connection:
  ```bash
  prvet doctor
  ```
* **CI Gating Checks:** Validate if a pull request violates threshold rules and has unresolved critical/high issues. Exits `0` on pass, or `1` on failure:
  ```bash
  prvet gate check --pr 12 --repo owner/name
  ```
* **System Deployment:** Bring up or tear down your environment stack on compose, AWS, Azure, or Kubernetes:
  ```bash
  prvet deploy --target compose
  prvet destroy --target compose
  ```

---

## 4. Install as a GitHub App (recommended)

No personal tokens, org-wide, one webhook, and the merge gate shows up as a **check run** you can make required in branch protection.

1. Set `PUBLIC_URL` (API, reachable by GitHub — e.g. an ngrok URL in dev) and `WEB_URL` in `.env`, restart the API.
2. **Configure → GitHub / Forges → Register app on GitHub.** You are sent to GitHub's manifest flow, approve, and land back in the UI with the app created.
3. Click **Install on GitHub**, pick repositories. Each installation appears as a connection; its repositories are enabled automatically and every PR gets reviewed.

Personal-access-token connections still work for GitLab, Azure DevOps, self-hosted forges and quick local experiments.

## 5. How a PR is reviewed

`graph → sast → triage → review → verify → gate → post`

1. **Graph** — diff lines are mapped onto the symbol graph from the latest baseline; callers of every changed symbol (blast radius, depth 2) are collected.
2. **SAST** — Semgrep runs the bundled rules (`packages/rules/semgrep`) plus rules authored in **Configure → Rules** on the head-SHA contents.
3. **Triage** — the *fast* model routes each file to `skip | fast | deep`; lockfiles/docs are skipped and security-sensitive paths or widely-called symbols are forced to `deep` without asking.
4. **Review** — the fast or deep model reviews each file with the callers' source packed into the prompt.
5. **Verify** — critical/high LLM findings are re-checked by the fast model; unconfirmed ones are dropped.
6. **Gate** — SAST and LLM findings are deduplicated and fingerprinted (stable across line shifts; findings that vanish on the next push auto-resolve), a risk score (0–100) and a `pass|block` decision are written, and posted as a check run (App) or commit status (PAT).
7. **Post** — one batched review: summary, severity table, findings, blast-radius table, inline comments.

## 6. Code Explorer

**Overview → Code Explorer** shows the symbol graph behind blast-radius review: file tree, code with symbol markers, an interactive **dependency graph** of file imports, and an inspector with outline · imports · imported-by · callers · callees · **blast radius** for any symbol. Fuzzy symbol search is in the header; the raw parse tree is still available as a tab.

### B. SonarQube-style Repos Workspace
Review baseline metrics, security ratings (A–E grades), and open issues inside the master-detail explorer. Supports manually dismissing false positives directly from the panel.

---

## 7. Local Development (Without Docker)

To run the backend API, background worker, and Next.js web application individually on your host system:

### A. Prerequisites
Ensure PostgreSQL and Redis databases are running locally:
```bash
# Example using Homebrew on macOS
brew services start postgresql@14
brew services start redis
```

### B. Run API Server
From the project root (install all workspace packages once with `uv sync --all-packages --all-extras`; the `sast` extra brings Semgrep):
```bash
cd apps/api
uv run uvicorn crv_api.main:app --reload --port 8080
```

### C. Run Async Worker
From the project root:
```bash
cd apps/worker
uv run python -m crv_worker.main
```

### D. Run Next.js Web App
From the project root:
```bash
cd apps/web
pnpm install
pnpm dev
```
Open [http://localhost:3737](http://localhost:3737) in your browser.

---

## Docs & Architecture

* [`PRD.md`](PRD.md) — Product requirements, database schema, queue mechanisms, and parser interfaces.
* [`plan.md`](plan.md) — Multi-cloud deployment guide, cost structures, and execution blueprints.
