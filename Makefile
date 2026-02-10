.PHONY: help install lint format typecheck test check graph clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies + workspace packages
	uv sync
	uv pip install -e libs/* -e apps/*

# ── Scope resolution ────────────────────────────────────
# Usage:
#   make lint                     → full run
#   make lint SCOPE=auto          → only affected packages (vs origin/main)
#   make lint SCOPE="libs/shared" → explicit paths
#
# Same for: typecheck, test, check

_resolve_scope = $(if $(filter auto,$(SCOPE)),\
	$(shell uv run python scripts/affected.py --base origin/main 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(d.get('$(1)',[])) if not d['all'] else '.')" 2>/dev/null || echo "."),\
	$(if $(SCOPE),$(SCOPE),.))

lint: ## Lint code [SCOPE=auto|paths]
	$(eval LINT_PATHS := $(call _resolve_scope,lint_paths))
	@if [ "$(LINT_PATHS)" = "." ]; then \
		echo "→ Linting: all packages"; \
	else \
		echo "→ Linting: $(LINT_PATHS)"; \
	fi
	uv run ruff check $(LINT_PATHS)
	uv run ruff format --check $(LINT_PATHS)
	uv run lint-imports

format: ## Auto-format code [SCOPE=auto|paths]
	$(eval FMT_PATHS := $(call _resolve_scope,lint_paths))
	uv run ruff check --fix $(FMT_PATHS)
	uv run ruff format $(FMT_PATHS)

typecheck: ## Type check [SCOPE=auto|paths]
	$(eval TC_PATHS := $(call _resolve_scope,src_paths))
	@if [ "$(TC_PATHS)" = "." ]; then \
		echo "→ Type checking: all packages"; \
	else \
		echo "→ Type checking: $(TC_PATHS)"; \
	fi
	uv run ty check $(TC_PATHS)

test: ## Run tests with coverage [SCOPE=auto|paths]
	$(eval TEST_PATHS := $(call _resolve_scope,test_paths))
	@if [ "$(TEST_PATHS)" = "." ]; then \
		echo "→ Testing: all packages"; \
	else \
		echo "→ Testing: $(TEST_PATHS)"; \
	fi
	uv run pytest $(TEST_PATHS) --cov --cov-report=term-missing

check: ## Run all guardrails + lint + typecheck + test [SCOPE=auto|paths]
	uv run python scripts/check_deps.py
	bash scripts/check_lock.sh
	$(MAKE) lint SCOPE=$(SCOPE)
	$(MAKE) typecheck SCOPE=$(SCOPE)
	$(MAKE) test SCOPE=$(SCOPE)

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
