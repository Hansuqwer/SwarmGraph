.PHONY: install test lint format type docs serve-docs build clean smoke audit-scan security

UV := $(or $(shell command -v uv 2>/dev/null),/opt/homebrew/bin/uv)

install:
	$(UV) sync --all-extras --dev

test:
	$(UV) run pytest packages/swarm-shared/tests packages/hive-swarm/tests packages/ai-provider-swarm-gateway/tests

lint:
	$(UV) run ruff check packages/

format:
	$(UV) run ruff format --check packages/

type:
	$(UV) run pyright

docs:
	$(UV) run mkdocs build

serve-docs:
	uv run mkdocs serve

build:
	rm -rf dist
	$(UV) build --package swarm-shared --out-dir dist
	$(UV) build --package hive-swarm --out-dir dist
	$(UV) build --package ai-provider-swarm-gateway --out-dir dist

clean:
	rm -rf dist/ site/ .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +

smoke:
	$(UV) run python examples/01_smoke_stub_mode.py

audit-scan:
	@if git diff --cached | grep -E \
	  'sk-[a-z0-9]{20}|AKIA[0-9A-Z]{16}|gh[opusr]_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|Bearer [A-Za-z0-9._-]{20,}'; then \
	  echo "WARNING: potential secret detected; aborting commit" >&2; \
	  exit 1; \
	elif git diff --cached | grep -E -- \
	  '-----BEGIN [A-Z ]*PRIVATE KEY-----'; then \
	  echo "WARNING: potential secret detected; aborting commit" >&2; \
	  exit 1; \
	else \
	  echo "Token scan: clean"; \
	fi

security:
	$(UV) run bandit -r packages/swarm-shared/swarm_shared packages/hive-swarm/swarm packages/ai-provider-swarm-gateway/src -f screen
	$(UV) run pip-audit --desc --skip-editable
