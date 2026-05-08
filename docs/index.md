# SwarmGraph

SwarmGraph is a Python monorepo for type-safe AI swarms: Pydantic v2 schemas, LangGraph orchestration, and a multi-provider gateway.

Start with [Installation](getting-started/installation.md), then run the [Quickstart](getting-started/quickstart.md).

## Packages

- `swarm-shared`: shared primitives, redaction, pricing, audit signing
- `hive-swarm`: swarm graph, queen/worker nodes, consensus, HITL
- `ai-provider-swarm-gateway`: provider adapters, quota, CLI

## Current release

`v0.8.0`: HMAC-SHA256 audit signing + streaming HITL guards.
