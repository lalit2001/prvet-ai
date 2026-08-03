# Sentry Review — `crv`

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
| **System Admin** | `admin@sentry.review` | `admin123` | `admin` | Full Access (Dashboards, Rules Config, Forge Settings, AST Viewer) |
| **Standard User** | `user@sentry.review` | `user123` | `member` | Restricted Access (Read-only dashboards, PR findings; Configuration menus hidden) |

---

## 3. Go CLI (`crv`) Guide

The `crv` command-line utility acts as a deployment companion and CI pipeline gatekeeper. It does not require Go on the local machine once compiled.

### A. Compile the Binary
To compile the `crv` CLI binary from source:
```bash
go build -o crv cli/main.go
```

### B. Global System Installation
Move the compiled binary to a folder in your environment's `$PATH`:
```bash
sudo mv crv /usr/local/bin/crv
sudo chmod +x /usr/local/bin/crv
```

### C. Available CLI Commands
* **System Diagnostics:** Probe the status of your database, redis queue, object store, and api connection:
  ```bash
  crv doctor
  ```
* **CI Gating Checks:** Validate if a pull request violates threshold rules and has unresolved critical/high issues. Exits `0` on pass, or `1` on failure:
  ```bash
  crv gate check --pr 12 --repo owner/name
  ```
* **System Deployment:** Bring up or tear down your environment stack on compose, AWS, Azure, or Kubernetes:
  ```bash
  crv deploy --target compose
  crv destroy --target compose
  ```

---

## 4. Key Diagnostic Workspaces

### A. AST Workspace
Located under **Configure -> AST Viewer** (Admin only). It lets you select any file in your configured Git projects or paste custom code snippets:
1. Displays the raw **Source Code** and **Abstract Syntax Tree (AST)** side-by-side.
2. **Bidirectional Highlighting:** Click any code line to locate and highlight its corresponding AST node, or click any AST node to highlight and scroll to its code coordinate.

### B. SonarQube-style Repos Workspace
Review baseline metrics, security ratings (A–E grades), and open issues inside the master-detail explorer. Supports manually dismissing false positives directly from the panel.

---

## 5. Local Development (Without Docker)

To run the backend API, background worker, and Next.js web application individually on your host system:

### A. Prerequisites
Ensure PostgreSQL and Redis databases are running locally:
```bash
# Example using Homebrew on macOS
brew services start postgresql@14
brew services start redis
```

### B. Run API Server
From the project root:
```bash
cd apps/api
uv run uvicorn crv_api.main:app --reload --port 8000
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
