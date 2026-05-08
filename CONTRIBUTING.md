# Contributing to SwarmGraph

Thank you for your interest in contributing.

## Setup

```bash
# Requires uv — https://docs.astral.sh/uv/
git clone https://github.com/Hansuqwer/SwarmGraph.git
cd SwarmGraph
uv sync --all-extras --dev
```

## Before submitting a PR

```bash
make lint     # ruff check
make type     # pyright
make test     # pytest all packages
```

All three must pass. CI enforces them.

## Security rules

- Never include real API keys, tokens, or secrets in any file.
- Run `make audit-scan` before every commit.
- See [SECURITY.md](SECURITY.md) for full policy.

## Package layout

```
packages/
  swarm-shared/        # Pydantic primitives, audit, pricing
  hive-swarm/          # Queen/worker graph, consensus, HITL
  ai-provider-swarm-gateway/  # CLI, quota, provider adapters
```

Each package has its own `tests/` directory. Add tests alongside code.

## Commit style

`type(scope): description` — e.g. `feat(audit): add verify_chain CLI flag`

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.

## Reporting issues

Use [GitHub Issues](https://github.com/Hansuqwer/SwarmGraph/issues).
For security vulnerabilities, use [Security Advisories](https://github.com/Hansuqwer/SwarmGraph/security/advisories/new) — never a public issue.
