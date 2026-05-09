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

## Programmatic Loading

Use `JSONLBackend` for local audit logs and `S3AuditBackend` for partitioned S3 logs:

```python
from swarm_shared.audit import verify_chain
from swarm_shared.audit_backends import JSONLBackend, S3AuditBackend

local = JSONLBackend("audit.jsonl")
records = local.load("swarm-123", start_date="2026-05-01", end_date="2026-05-09")
verify_chain(records, secret=b"replace-with-test-secret")

s3 = S3AuditBackend(bucket="audit-bucket", prefix="audit")
records = s3.load("swarm-123", start_date="2026-05-01", end_date="2026-05-09")
```

Dates must use `YYYY-MM-DD`. Loading preserves verification responsibility: always run `verify_chain()` with the expected secret, and pin `expected_count` / `expected_head_hash` when those values are known.

`S3AuditBackend.restore_swarm(...)` is a compatibility alias for `restore_archive(...)`:

```python
restored = s3.restore_swarm("swarm-123", days=7, tier="Bulk")
```
