# ADR 0003: Multi-Tenant Quota

Status: Accepted

Decision: Quota state is tenant-scoped via `tenant_id` and CLI `--tenant`.

Rationale: avoid cross-tenant quota bleed and support gateway deployments with shared provider credentials.
