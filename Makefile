.PHONY: install test lint format type docs serve-docs build clean smoke audit-scan security

install:
	uv sync --all-extras --dev

test:
	uv run pytest packages/swarm-shared/tests packages/hive-swarm/tests packages/ai-provider-swarm-gateway/tests

lint:
	uv run ruff check packages/

format:
	uv run ruff format --check packages/

type:
	uv run pyright

docs:
	uv run mkdocs build

serve-docs:
	uv run mkdocs serve

build:
	uv build packages/swarm-shared packages/hive-swarm packages/ai-provider-swarm-gateway

clean:
	rm -rf dist/ site/ .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +

smoke:
	uv run python examples/01_smoke_stub_mode.py

audit-scan:
	@if git diff --cached | grep -iE \
	  'sk-[a-z0-9]{20}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36}|Bearer [a-zA-Z0-9]{20,}'; then \
	  echo "WARNING: potential secret detected; aborting commit" >&2; \
	  exit 1; \
	else \
	  echo "Token scan: clean"; \
	fi

security:
	uv run bandit -r packages/swarm-shared/swarm_shared packages/hive-swarm/swarm packages/ai-provider-swarm-gateway/src -f screen
	uv run pip-audit --desc --skip-editable
