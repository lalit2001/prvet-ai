# Sentry Review — `crv`

Self-hosted AI code review that ships with your codebase, not with your source code leaving the network.

- **What it does:** reviews PRs with their blast radius (callers across the repo, not just the diff), scores health at baseline, tracks drift weekly, gates merges on unresolved critical findings with auditable bypass.
- **Where it runs:** anywhere. `docker compose up` on your laptop, one Terraform module on AWS or Azure, one Helm chart on any Kubernetes, or a single VM in an airgapped datacenter.
- **What LLM it uses:** any. OpenAI-compatible endpoint config — Anthropic, OpenAI, Bedrock, Azure OpenAI, vLLM, Ollama. One config change, zero code change.

## Docs

- [`PRD.md`](PRD.md) — product requirements, architecture, data model, adapter contracts, feature specs.
- [`plan.md`](plan.md) — delivery plan, deployment guides, per-SKU cost model, container strategy, open decisions.

## Quick start (compose)

```bash
cp deploy/compose/.env.example .env
# edit .env: LLM_BASE_URL, LLM_API_KEY, forge token
docker compose --project-directory deploy/compose up -d
open http://localhost:3737
```

## Repo layout

See [`PRD.md` §7](PRD.md).

## License

MIT — see [`LICENSE`](LICENSE).
