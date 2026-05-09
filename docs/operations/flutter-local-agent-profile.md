# Flutter Local Agent Profile

Use this profile when SwarmGraph is driving local Flutter work through MCP tools.
Install it as an optional workflow extra; the base gateway install does not need
the MCP SDK or Flutter tooling:

```bash
pip install 'ai-provider-swarm-gateway[flutter]'
```

```bash
export AI_PROVIDER_GATEWAY_MCP_ALLOWED_ROOTS="$HOME/code/my_flutter_app"
export HIVE_SWARM_AUDIT_SECRET="replace-with-local-random-dev-secret"
```

Recommended `SwarmConfig` values for important local workflows:

```python
SwarmConfig(
    audit_signing_enabled=True,
    audit_fail_closed=True,
    audit_log_path="audit/{tenant}/{swarm_id}.jsonl",
)
```

The dev secret is local only. Rotate it before real production use.

Verify a produced audit log:

```bash
uv run ai-provider-gateway audit verify audit/default/<swarm-id>.jsonl
```

Skip hosted-service concerns for this profile: remote audit backends, alerts,
dashboards, Redis/Postgres quota, and container health checks.
