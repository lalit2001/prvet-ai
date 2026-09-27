# Configuration

Two layers only. See [plan.md §14](../plan.md).

1. **Environment** — set once per deployment via `.env` or the chosen SecretsAdapter.
2. **Per-repo `.crv.yml`** — committed to each repo's default branch.

**All runtime knobs live in the web UI** (`/admin/*`). The CLI does not set any of them.


## Public URLs (GitHub App, check-run links)

| Variable | Default | Purpose |
|---|---|---|
| `PUBLIC_URL` | `http://localhost:8080` | Where forges reach the API: app-level webhook `…/api/v1/webhooks/github-app/{app}` and the manifest callback. Must be reachable from GitHub (use a tunnel in dev). |
| `WEB_URL` | `http://localhost:3737` | Where humans reach the UI: post-install redirect and the "details" link on check runs / commit statuses. |
