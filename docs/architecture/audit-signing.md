# Audit Signing

SwarmGraph emits tamper-evident audit records for consensus, approval, worker,
and streaming HITL decisions when audit signing is enabled.

- HMAC-SHA256 signature
- chained `prev_hash`
- monotonic `sequence`
- JSONL persistence
- optional S3 JSONL partitions

Verify logs:

```bash
HIVE_SWARM_AUDIT_SECRET=<secret> uv run ai-provider-gateway audit verify audit.jsonl
```

Insertion, deletion, reorder, and field tampering break verification.

## Secret Policy

Use a high-entropy secret with at least 32 random bytes. Generate one with:

```bash
python - <<'PY'
import base64, secrets
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
```

Store it outside the repository, usually in `HIVE_SWARM_AUDIT_SECRET` or your
deployment secret manager. Never commit the value, paste it into tickets, or log
it. Environment variable names are safe to reference; values are not.

## Rotation

Audit signatures are verified with the secret that was active when the record was
written. Rotation therefore creates epochs:

- records before rotation verify with the old secret
- records after rotation verify with the new secret
- the handover point should be recorded in deployment metadata

Recommended rotation cadence is at least every 90 days for production systems,
and immediately after any suspected exposure.

## Compromise Response

If an audit secret may have leaked:

1. Revoke the secret in the deployment secret manager.
2. Generate and deploy a new 32-byte secret.
3. Preserve old logs and old secret material only in your incident vault if you
   must verify historical records.
4. Pin future verification with `--expected-head-hash` and `--expected-count` so
   wholesale log replacement is detected.
5. Treat records signed after the exposure time and before rotation as suspect.

## Payload Size

Local JSONL appends reject records larger than 4000 bytes to preserve practical
POSIX atomic-append behavior. Store large artifacts externally and place hashes or
URIs in audit payloads. Use the S3 backend for durable cloud retention.
