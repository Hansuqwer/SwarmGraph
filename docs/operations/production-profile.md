# Production Profile

Run this preflight before hosted deployments accept traffic:

```bash
export AI_PROVIDER_GATEWAY_TENANT=tenant-1
export HIVE_SWARM_AUDIT_SECRET='replace-with-32-plus-random-bytes'
export HIVE_SWARM_AUDIT_SIGNING_ENABLED=true
export HIVE_SWARM_AUDIT_FAIL_CLOSED=true
export HIVE_SWARM_AUDIT_LOG_PATH='/var/lib/swarmgraph/audit/{tenant}/{swarm_id}.jsonl'
ai-provider-gateway profile production --check
```

Optional regulated/high-assurance setting:

```bash
export HIVE_SWARM_AUDIT_FSYNC_ENABLED=true
```

`HIVE_SWARM_AUDIT_FSYNC_ENABLED` increases durability against power loss but reduces append throughput.

Optional service shell:

```bash
uvicorn ai_provider_swarm_gateway.service:create_app --factory --host 0.0.0.0 --port 8000
```

Install with `ai-provider-swarm-gateway[service]`. The service exposes `/healthz`, `/readyz`, and `/metrics` only; route/swarm mutation APIs are intentionally not enabled.

## Container Deployment

For local container isolation or hosted deployments, see:
- [OrbStack Local Isolation](./orbstack-local-isolation.md) - Docker-compatible local container runtime guide
