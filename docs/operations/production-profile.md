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
