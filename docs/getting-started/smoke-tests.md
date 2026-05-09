# Smoke Tests

Stub mode:

```bash
uv run python examples/01_smoke_stub_mode.py
```

Tier-3 gateway smoke:

```bash
HIVE_SWARM_LLM_PROVIDER=<provider-id> \
HIVE_SWARM_LLM_MODEL=<model-id> \
uv run python examples/02_smoke_tier3_gateway.py
```

Set the provider-specific API key required by your selected gateway adapter before running live smoke tests.
