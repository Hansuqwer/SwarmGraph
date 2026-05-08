# Audit Verification

```bash
HIVE_SWARM_AUDIT_SECRET=<secret> \
uv run ai-provider-gateway audit verify path/to/audit.jsonl
```

Exit codes:

- `0`: clean
- `1`: missing secret/import issue
- `2`: malformed JSONL
- `3`: chain/signature mismatch
