.PHONY: help install lint format typecheck test check graph clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies + workspace packages
	uv sync
	uv pip install -e libs/* -e apps/*

lint: ## Run ruff linter + import boundary checks
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

format: ## Auto-format code with ruff
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Run ty type checker
	uv run ty check

test: ## Run tests with coverage
	uv run pytest --cov --cov-report=term-missing

check: ## Run all guardrails + lint + typecheck + test
	uv run python scripts/check_deps.py
	bash scripts/check_lock.sh
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test

graph: ## Generate dependency graph
	uv run python scripts/dep_graph.py

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache .ty htmlcov .coverage dist build

new-lib: ## Create a new library: make new-lib name=mylib
	@test -n "$(name)" || (echo "Usage: make new-lib name=mylib" && exit 1)
	uv init --lib --build-backend uv libs/$(name)
	rm -rf libs/$(name)/.git libs/$(name)/.python-version libs/$(name)/.gitignore
	@echo "✅ Created libs/$(name)"

new-app: ## Create a new app: make new-app name=myapp
	@test -n "$(name)" || (echo "Usage: make new-app name=myapp" && exit 1)
	uv init --app --no-readme --build-backend uv apps/$(name)
	rm -rf apps/$(name)/.git apps/$(name)/.python-version apps/$(name)/.gitignore
	@echo "✅ Created apps/$(name)"
