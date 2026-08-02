# Configuration

Two layers only. See [plan.md §14](../plan.md).

1. **Environment** — set once per deployment via `.env` or the chosen SecretsAdapter.
2. **Per-repo `.crv.yml`** — committed to each repo's default branch.

**All runtime knobs live in the web UI** (`/admin/*`). The CLI does not set any of them.
