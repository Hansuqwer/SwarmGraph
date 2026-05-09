# SwarmGraph

[![CI](https://github.com/Hansuqwer/SwarmGraph/actions/workflows/ci.yml/badge.svg)](https://github.com/Hansuqwer/SwarmGraph/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org)

A Pydantic-strict, voting-based, audit-first LangGraph runtime for regulated or high-assurance multi-agent workflows where consensus, replay safety, signed audit trails, tenant isolation, and deterministic orchestration matter more than free-form conversational handoffs.

SwarmGraph is not an OpenAI-Swarm-style handoff framework. It is a Pydantic-strict, voting-based, audit-first LangGraph runtime for parallel agent deliberation, consensus, HITL approval, and signed execution records.


## When to Use SwarmGraph

| Question | Use |
|---|---|
| Need conversational handoff between specialists? | `langgraph-swarm` or raw LangGraph |
| Need sequential agent relay with active-agent memory? | `langgraph-swarm` |
| Need typed fan-out, votes, consensus, HITL, and audit chains? | SwarmGraph |
| Need a simple single-agent chatbot? | Not SwarmGraph |
| Need a broad tool-use agent framework? | Raw LangGraph, LangChain Agents, or CrewAI-style frameworks |

Decision flow: single chatbot → not SwarmGraph; conversational handoff → `langgraph-swarm`; typed consensus plus auditable execution → SwarmGraph.

---

## Quick start

```bash
# 1. Install (requires uv — https://docs.astral.sh/uv/)
uv sync --all-extras --dev

# 2. Run all tests
uv run pytest packages/

# 3. Try the CLI
uv run ai-provider-gateway --help
uv run swarmgraph --help  # alias for ai-provider-gateway
uv run ai-provider-gateway swarm --prompt "implement add(a,b)" --anti-drift off --max-agents 3 --json

# Optional local dashboard
uv run ai-provider-gateway dashboard

# Verify signed local/S3 audit logs
uv run ai-provider-gateway audit verify audit.jsonl --expected-count 10
uv run ai-provider-gateway audit verify s3://my-bucket/audit --swarm-id swarm-123
```

For gateway-backed execution with a live model:

```bash
HIVE_SWARM_LLM_BACKEND=gateway \
uv run ai-provider-gateway swarm \
  --prompt "implement add(a,b)" \
  --backend gateway --provider <provider-id> --model <model-id> \
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
│  │ primitives   │   │ LangGraph    │   │ provider   │  │
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
- **Local/S3 audit loading** — JSONL and S3 backends support swarm/date-range loading
- **Streaming HITL guards** — per-chunk regex denylist + length cap
- **Multi-provider gateway** — provider adapters, routing, and per-role overrides
- **Cost tracking** — per-call USD estimate, rolled up across workers
- **S3 audit backend** — partitioned JSONL audit logs, conditional append, restore CLI
- **Optional monitoring TUI** — Textual dashboard with consensus trend + quota/resource panels
- **Semantic response cache** — SQLite exact-match + cosine-similarity lookup
- **Resource-aware scaling** — optional runtime agent cap from available local RAM
- **Encrypted account vault** — Fernet-encrypted local key/session store, no plaintext fallback
- **Grok/xAI adapter** — OpenAI-compatible mocked-test provider integration
- **Release provenance** — GitHub artifact attestation for release distributions

Security note: browser auth import is explicit opt-in only and never prints tokens:

```bash
uv run ai-provider-gateway auth import-browser chatgpt --dry-run
uv run ai-provider-gateway auth import-browser chatgpt --vault-path ~/.ai_provider_gateway/secrets.json.enc
```

---

## Documentation

Full docs at [docs/](docs/) (mkdocs-material site — run `make serve-docs`).

`docs/` contains user-facing reference material. `docs/history/` is a provenance and process archive; it is useful for audit review but not required reading for normal users.

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

CI publishes `coverage.xml` as an artifact from the Python 3.11 Ubuntu job.

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
