# SwarmGraph

[![CI](https://github.com/Hansuqwer/SwarmGraph/actions/workflows/ci.yml/badge.svg)](https://github.com/Hansuqwer/SwarmGraph/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org)

**Type-safe AI agent swarms with Pydantic v2, LangGraph, and a multi-provider gateway.**

SwarmGraph lets you compose small, specialised agents into collaborative swarms that reach consensus, validate every message with Pydantic schemas, and route LLM calls through a provider-agnostic gateway — all locally, with free or commercial models.

---

## Quick start

```bash
# 1. Install (requires uv — https://docs.astral.sh/uv/)
uv sync --all-extras --dev

# 2. Run all tests
uv run pytest packages/

# 3. Try the CLI
uv run ai-provider-gateway --help
uv run ai-provider-gateway swarm --prompt "implement add(a,b)" --anti-drift off --max-agents 3 --json
```

For gateway-backed execution with a live model:

```bash
HIVE_SWARM_LLM_BACKEND=gateway \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<your-key> \
uv run ai-provider-gateway swarm \
  --prompt "implement add(a,b)" \
  --backend gateway --provider 9router --model kc/kilo-auto/free \
  --anti-drift off --max-agents 3 --json
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      SwarmGraph                         │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│  │ swarm-shared │   │  hive-swarm  │   │  gateway   │  │
│  │              │◄──│              │◄──│            │  │
│  │ Pydantic     │   │ Queen/Worker │   │ CLI + quota│  │
│  │ primitives   │   │ LangGraph    │   │ 9router/   │  │
│  │ audit chain  │   │ consensus    │   │ OpenAI/... │  │
│  └──────────────┘   └──────────────┘   └────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Packages

| Package | Description | Install |
|---|---|---|
| [`swarm-shared`](packages/swarm-shared/) | Pydantic primitives, audit chain, pricing, redaction | `pip install swarm-shared` |
| [`hive-swarm`](packages/hive-swarm/) | Queen/worker graph, consensus, HITL, anti-drift | `pip install hive-swarm` |
| [`ai-provider-swarm-gateway`](packages/ai-provider-swarm-gateway/) | Multi-provider gateway, quota, CLI | `pip install ai-provider-swarm-gateway` |

---

## Features

- **Pydantic v2 discipline** — every model frozen + validated; no silent coercions
- **LangGraph orchestration** — queen fan-out, worker Send, conditional edges
- **3-protocol consensus** — Raft (default), BFT, simple-majority
- **Interactive HITL** — single-use tokens, risk-gated approval prompts
- **Multi-tenant quota** — per-tenant daily/window request + token limits
- **3-mode anti-drift** — off / keyword / embedding (cosine similarity)
- **HMAC-SHA256 audit chain** — tamper-evident, chained, verifiable offline
- **Streaming HITL guards** — per-chunk regex denylist + length cap
- **Multi-provider gateway** — 9router, OpenAI-compatible; per-role overrides
- **Cost tracking** — per-call USD estimate, rolled up across workers

---

## Documentation

Full docs at [docs/](docs/) (mkdocs-material site — run `make serve-docs`).

Key pages:
- [Getting started](docs/getting-started/installation.md)
- [Architecture overview](docs/architecture/overview.md)
- [Audit signing](docs/architecture/audit-signing.md)
- [Multi-tenant quota](docs/architecture/multi-tenant-quota.md)
- [Gateway CLI reference](docs/reference/gateway-cli.md)
- [Security](docs/operations/security.md)

---

## Development

```bash
make install      # uv sync --all-extras --dev
make test         # pytest packages/
make lint         # ruff check packages/
make type         # pyright packages/
make smoke        # python examples/01_smoke_stub_mode.py
make serve-docs   # mkdocs serve (http://localhost:8000)
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions require:
- Tests for new behaviour
- No credentials in any file (see [SECURITY.md](SECURITY.md))
- Passing `make lint` + `make type`

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history (v0.1.0 → v0.8.0).

Patch history and orchestrator prompts are preserved verbatim under [docs/history/](docs/history/).

---

## License

[MIT](LICENSE) © 2026 Hansuqwer
