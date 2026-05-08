# Audit Signing

v0.8.0 adds tamper-evident audit records:

- HMAC-SHA256 signature
- chained `prev_hash`
- monotonic `sequence`
- JSONL persistence

Verify logs:

```bash
HIVE_SWARM_AUDIT_SECRET=<secret> uv run ai-provider-gateway audit verify audit.jsonl
```

Insertion, deletion, reorder, and field tampering break verification.
