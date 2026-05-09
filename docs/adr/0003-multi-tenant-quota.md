# ADR 0003: Multi-Tenant Quota

Status: Accepted

## Context

The gateway can serve multiple users or automation tenants while sharing provider
adapters and local quota storage. Quota bleed between tenants would create unfair
throttling and misleading cost/accounting data.

## Decision

Quota state is tenant-scoped via `tenant_id`, CLI `--tenant`, and environment
configuration. Tenant-specific storage paths isolate usage counters.

## Consequences

Operators can run shared gateway deployments without mixing tenant usage. The
tradeoff is that callers must propagate tenant context consistently.

## Alternatives Considered

A single global quota store was rejected because it is simpler but unsafe for
multi-tenant use. Provider-account-only scoping was insufficient because one
tenant can use multiple providers and one provider can serve multiple tenants.
