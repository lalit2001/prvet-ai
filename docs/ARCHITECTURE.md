# Architecture

Six components. See [PRD §6](../PRD.md).

The **import-boundary rule** — no cloud SDK outside `packages/adapters/` — is the single most important architectural invariant. It is enforced by `import-linter` in CI (see `pyproject.toml`).
