# Flutter Local Agent Handover

## Summary

- Added fail-closed MCP workspace allowlist via `AI_PROVIDER_GATEWAY_MCP_ALLOWED_ROOTS`.
- Added JSON-line stderr logging and an in-memory counter for MCP rejects.
- Added S3 vault pull decrypt sanity-check before atomic replacement.
- Added Flutter-aware gitleaks config and pre-commit hook.
- Added dev-safe smoke coverage and local Flutter/MCP docs.
- Added local audit profile and vault backup/restore docs.
- Kept Flutter/MCP optional via `ai-provider-swarm-gateway[flutter]`; the base install has no MCP SDK dependency.

## Sources

- Context7 `/modelcontextprotocol/python-sdk`: FastMCP tools use `mcp.tool()` decorators and can return structured tool results.
- Context7 `/fastapi/typer`: Typer supports `BadParameter`, `Exit`, and `CliRunner.invoke()` for CLI tests.
- Context7 `/pyca/cryptography`: Fernet `decrypt()` verifies integrity and raises `InvalidToken` for malformed/tampered tokens.
- Context7 `/gitleaks/gitleaks`: gitleaks supports `[extend] useDefault = true`, custom `[[rules]]`, and `[[allowlists]]` in TOML.
- grep.app `is_relative_to(`: public OSS patterns use resolved `Path.is_relative_to()`/`relative_to()` for root containment, including `langchain-ai/langgraph`, `marimo-team/marimo`, and `Significant-Gravitas/AutoGPT`.

## Verification Commands

Run after implementation:

```bash
uv run ruff check packages/
uv run pyright
uv run pytest packages/ai-provider-swarm-gateway/tests/test_mcp_toolbox_cli.py
uv run pytest packages/ai-provider-swarm-gateway/tests/test_mcp_allowlist.py
uv run pytest packages/ai-provider-swarm-gateway/tests/test_pool_cli.py
uv run pytest packages/ai-provider-swarm-gateway/tests/test_dev_safe_smoke.py
uv run pytest packages/
```

Secret scanning, if installed locally:

```bash
pre-commit run --all-files
gitleaks detect --no-git --source . --config .gitleaks.toml --redact
```

## Deferred

- Dockerfile
- health/readiness checks
- resource limits
- deployment runbook
- Redis/Postgres quota backend
- PostgresSaver wiring
- audit metrics/alerts
- dashboards
- SBOM typed predicate
- S3 live tests
- JSONL append stress test

## Rollback

- MCP allowlist: remove `enforce_allowed_path()` calls in `mcptoolbox.py`.
- Vault sanity: remove `verify_vault_file()` call in `pool_sync --pull`.
- Secret scanning: remove `.gitleaks.toml` and the gitleaks pre-commit hook.
- Docs are additive and safe to revert independently.
