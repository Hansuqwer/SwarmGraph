# SwarmGraph Agent Instructions

Work in small, independently reviewable PRs. Prefer issue-driven changes over broad patch bundles.

## Required Workflow

- Inspect the current repo before editing; do not rely on stale patch context.
- Keep changes minimal and scoped to one issue.
- Do not commit generated review bundles, local scratch files, `.DS_Store`, PDFs, or `docs/patches/` unless explicitly requested.
- Never include secrets, provider keys, bearer tokens, or copied authorization headers.
- Preserve stub/no-network defaults; real provider calls must remain opt-in.
- Do not make LangGraph mandatory for lightweight package installs unless the issue explicitly requests it.

## Validation

Run the smallest relevant focused tests, then the standard checks when practical:

```bash
/opt/homebrew/bin/uv run ruff check packages/
/opt/homebrew/bin/uv run pyright
/opt/homebrew/bin/uv run pytest packages/swarm-shared/tests packages/hive-swarm/tests packages/ai-provider-swarm-gateway/tests --tb=short -q
```

For docs changes:

```bash
/opt/homebrew/bin/uv run mkdocs build --strict
```

For release/workflow changes, validate locally where possible and explain what cannot be run.

## PR Expectations

- Link one issue.
- Include risk and rollback notes.
- Include exact validation commands and results.
- Call out residual risks rather than hiding them.
