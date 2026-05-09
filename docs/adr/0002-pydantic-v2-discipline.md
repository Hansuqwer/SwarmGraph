# ADR 0002: Pydantic v2 Discipline

Status: Accepted

## Context

SwarmGraph passes state through LangGraph nodes, JSON round-trips, audit payloads,
and CLI surfaces. Silent coercion or extra fields would make replay and audit
verification less trustworthy.

## Decision

Core state and boundary objects use Pydantic v2 models with explicit field
constraints. Boundary models reject unexpected data where practical and keep JSON
serialization predictable.

## Consequences

Validation failures happen early, schema evolution is deliberate, and audit records
can be signed over stable payloads. The tradeoff is more boilerplate and occasional
adapter code for third-party objects.

## Alternatives Considered

Plain dictionaries were rejected for core state because they hide schema drift.
Dataclasses were considered but do not provide the same validation and JSON-schema
behavior without additional libraries.
