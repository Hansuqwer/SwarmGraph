# Smoke Tests

Stub mode:

```bash
uv run python examples/01_smoke_stub_mode.py
```

Tier-3 gateway smoke:

```bash
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<your-key> \
uv run python examples/02_smoke_tier3_gateway.py
```
