.PHONY: help dev check lint type test build up down doctor migrate clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: up ## Bring up compose + migrate + tail logs
	docker compose --project-directory deploy/compose logs -f api worker

up: ## docker compose up
	docker compose --project-directory deploy/compose up -d

down: ## docker compose down
	docker compose --project-directory deploy/compose down

check: lint type test ## Full local CI: lint + type + test

lint:
	uv run ruff check .
	uv run ruff format --check .
	cd apps/web && pnpm lint

type:
	uv run mypy packages/core/src packages/adapters/src
	cd apps/web && pnpm typecheck
	uv run lint-imports

test:
	uv run pytest -q
	cd apps/web && pnpm test
	cd cli && go test ./...

build:
	docker build -f docker/api.Dockerfile -t crv-api:dev .
	docker build -f docker/worker.Dockerfile -t crv-worker:dev .
	docker build -f docker/web.Dockerfile -t crv-web:dev .

migrate:
	uv run alembic -c migrations/alembic.ini upgrade head

doctor:
	cd cli && go run . doctor

clean:
	rm -rf .venv .mypy_cache .pytest_cache .ruff_cache dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
