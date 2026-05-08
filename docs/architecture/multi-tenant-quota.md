# Multi-Tenant Quota

Gateway quota can be scoped by tenant:

```bash
uv run ai-provider-gateway quota increment --provider openai --requests 1 --tenant alice
uv run ai-provider-gateway quota show --tenant alice --json
```

Tenant storage is isolated by `QuotaTracker(tenant_id=...)` and CLI `--tenant` flags.
