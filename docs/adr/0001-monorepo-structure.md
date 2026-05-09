# ADR 0001: Monorepo Structure

Status: Accepted

## Context

SwarmGraph is split into shared primitives, orchestration runtime, and gateway/CLI
concerns. Changes often cross those boundaries: audit records are defined in
`swarm-shared`, emitted by `hive-swarm`, and verified through the gateway CLI.

## Decision

Use one GitHub repository with three package directories under `packages/`:

- `swarm-shared`
- `hive-swarm`
- `ai-provider-swarm-gateway`

## Consequences

This allows atomic changes, shared CI, shared documentation, and one lockfile for
release hardening. The tradeoff is a larger checkout and more care around package
boundaries.

## Alternatives Considered

Separate repositories would reduce per-package noise but make cross-package audit,
graph, and CLI changes harder to review and release consistently.
