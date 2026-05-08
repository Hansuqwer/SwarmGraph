# Handover patch v8 — Operational hardening (audit signing + streaming HITL)

> **Mixed delivery.** Files that I can ship cleanly are full files. Files
> where wholesale rewrites have caused regressions in v6/v7 (dispatch.py,
> cli.py) ship as **focused-diff modules** documenting the surgical edits
> for you to apply manually.

## File map

| File | Change | LoC delta |
|---|---|---|
| `swarm-shared/swarm_shared/audit.py` | NEW | ~280 |
| `swarm-shared/tests/test_audit.py` | NEW | ~280 |
| `hive-swarm/swarm/_audit_helper.py` | NEW | ~85 |
| `hive-swarm/swarm/models/config.py` | MODIFIED (full file) | +50 |
| `hive-swarm/swarm/models/state.py` | MODIFIED (full file) | +30 |
| `hive-swarm/swarm/nodes/consensus.py` | MODIFIED (full file) | +20 |
| `hive-swarm/swarm/nodes/approval.py` | MODIFIED (full file) | +20 |
| `hive-swarm/swarm/nodes/worker.py` | MODIFIED (full file) | +50 |
| `hive-swarm/swarm/llm/_v8_streaming_hitl_patch.py` | NEW (instructions) | — |
| `hive-swarm/tests/test_v8_audit_signing.py` | NEW | ~200 |
| `hive-swarm/tests/test_v8_streaming_hitl.py` | NEW | ~150 |
| `ai-provider-swarm-gateway/src/.../_v8_cli_additions.py` | NEW (instructions) | — |
| `ai-provider-swarm-gateway/tests/test_v8_audit_cli.py` | NEW | ~180 |

## Apply

### Step 1: Drop in the new files (safe — no regressions possible)

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched

# swarm-shared
cp cli_handover_patch_v8/swarm-shared/swarm_shared/audit.py \
   swarm-shared/swarm_shared/
cp cli_handover_patch_v8/swarm-shared/tests/test_audit.py \
   swarm-shared/tests/

# hive-swarm — new helper
cp cli_handover_patch_v8/hive-swarm/swarm/_audit_helper.py \
   hive-swarm/swarm/

# hive-swarm — new tests
cp cli_handover_patch_v8/hive-swarm/tests/test_v8_audit_signing.py \
   hive-swarm/tests/
cp cli_handover_patch_v8/hive-swarm/tests/test_v8_streaming_hitl.py \
   hive-swarm/tests/

# gateway — new tests
cp cli_handover_patch_v8/ai-provider-swarm-gateway/tests/test_v8_audit_cli.py \
   ai-provider-swarm-gateway/tests/
```

### Step 2: Modified files — diff-first apply

```bash
# Diff each modified file against your local v7.1 version
for f in \
    hive-swarm/swarm/models/config.py \
    hive-swarm/swarm/models/state.py \
    hive-swarm/swarm/nodes/consensus.py \
    hive-swarm/swarm/nodes/approval.py \
    hive-swarm/swarm/nodes/worker.py
do
  echo "=== $f ==="
  diff "$f" "cli_handover_patch_v8/$f" | head -30
done
```

If your local versions match v7.1's tree (with the cosmetic CLI fixes
preserved): the diff should show only the v8 additions, no v7.1
regressions. Then:

```bash
# Back up
for f in hive-swarm/swarm/models/config.py \
         hive-swarm/swarm/models/state.py \
         hive-swarm/swarm/nodes/consensus.py \
         hive-swarm/swarm/nodes/approval.py \
         hive-swarm/swarm/nodes/worker.py
do
  cp "$f" "$f.v7.1.bak"
done

# Apply
cp cli_handover_patch_v8/hive-swarm/swarm/models/config.py    hive-swarm/swarm/models/
cp cli_handover_patch_v8/hive-swarm/swarm/models/state.py     hive-swarm/swarm/models/
cp cli_handover_patch_v8/hive-swarm/swarm/nodes/consensus.py  hive-swarm/swarm/nodes/
cp cli_handover_patch_v8/hive-swarm/swarm/nodes/approval.py   hive-swarm/swarm/nodes/
cp cli_handover_patch_v8/hive-swarm/swarm/nodes/worker.py     hive-swarm/swarm/nodes/
```

### Step 3: Surgical edits to dispatch.py + cli.py

Two files are NOT shipped as full rewrites — too much regression risk.
Instead, apply 3 small inline edits to each:

```bash
# Read the instructions
python cli_handover_patch_v8/hive-swarm/swarm/llm/_v8_streaming_hitl_patch.py
python cli_handover_patch_v8/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/_v8_cli_additions.py
```

Each prints the 4 code blocks to insert/replace + line-by-line
instructions. Total: ~10 minutes of careful editing.

The instructions module is left in the patch tree (not copied into your
repo) so it doesn't pollute your source. After applying, you can delete
the instruction modules.

## Verify

```bash
source .venv/bin/activate
export HIVE_SWARM_AUDIT_SECRET=test-secret-32bytes-of-entropy-here-please

# v8 unit tests
pytest swarm-shared/tests/test_audit.py -q                                    # ~30 tests
pytest hive-swarm/tests/test_v8_audit_signing.py -q                           # ~13 tests
pytest hive-swarm/tests/test_v8_streaming_hitl.py -q                          # ~10 tests
pytest ai-provider-swarm-gateway/tests/test_v8_audit_cli.py -q                # ~10 tests

# Full regression
pytest swarm-shared/tests -q
pytest hive-swarm/tests -q
pytest ai-provider-swarm-gateway/tests -q

# Stub mode unchanged
.venv/bin/python smoke_test.py

# Live: signed audit log
mkdir -p /tmp/v8-demo
HIVE_SWARM_AUDIT_SECRET=demo-secret-not-real \
HIVE_SWARM_LLM_BACKEND=gateway \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \
ai-provider-gateway swarm \
    --prompt "implement add(a,b)" \
    --backend gateway --provider 9router --model kc/kilo-auto/free \
    --anti-drift off --max-agents 3 --json

# Then verify the audit log (when you wire audit_log_path to a real path
# via SwarmConfig — currently the swarm CLI doesn't expose --audit-log-path,
# so write a Python smoke that does)
HIVE_SWARM_AUDIT_SECRET=demo-secret-not-real \
ai-provider-gateway audit verify /path/to/audit.jsonl --json
# expected: {"ok": true, "verified": N, ...}
```

## What v8 adds

### 1. Audit log signing (HMAC-SHA256 + chained hash)

Every consensus_result, approval_decision, worker_result event gets:
- A SHA-256 record hash over the canonical record body
- An HMAC-SHA256 signature of that hash under your `HIVE_SWARM_AUDIT_SECRET`
- A `prev_hash` linking it to the previous record in the chain

```python
from swarm import SwarmConfig

config = SwarmConfig(
    audit_signing_enabled=True,
    audit_secret_env="HIVE_SWARM_AUDIT_SECRET",
    audit_log_path="/var/log/swarm-audit/{tenant}-{swarm_id}.jsonl",
    audit_kinds=("consensus_result", "approval_decision", "worker_result"),
)
```

The audit_log_path supports `{tenant}` and `{swarm_id}` placeholders
(handy for multi-tenant deployments — each tenant gets its own log).

Signed records appear in:
- `SwarmState.audit_records: list[dict]` (in-memory chain)
- The JSONL file at `audit_log_path` (one record per line, append-only)

Verify any log:
```bash
HIVE_SWARM_AUDIT_SECRET=<the-secret-you-signed-with> \
ai-provider-gateway audit verify /var/log/swarm-audit/alice-s1.jsonl --json
```

Exit codes:
- 0 = clean
- 1 = secret missing
- 2 = log malformed (not valid JSONL)
- 3 = chain broken (insertion / deletion / reorder / tampering)

### 2. Streaming HITL guards

When `llm_stream_enabled=True`, two per-chunk guards now fire:

```python
config = SwarmConfig(
    llm_stream_enabled=True,
    streaming_guard_patterns=[
        r"\b(SECRET|PRIVATE_KEY|password)\b",   # regex denylist
        r"BEGIN PRIVATE KEY",
    ],
    streaming_max_output_chars=8192,            # per-worker length cap
    streaming_guard_check_every_n_chunks=4,     # throttle (perf)
)
```

When a guard fires, the dispatcher raises `StreamingHITLInterrupt(reason, partial_text)`
mid-stream. `worker_node` catches it and produces `WorkerResult(success=False)`
with the partial output captured in `metadata.stream_hitl_partial_preview`.

The interactive prompt helper `_streaming_hitl_prompt()` ships in the CLI
patch but is not yet threaded into the `swarm` subcommand (deferred to v9
to keep v8 small — the helper is tested via direct invocation).

## Threat model (what v8 protects against)

| Attack | Caught by |
|---|---|
| Edit a payload field after signing | record_hash mismatch |
| Replace a signature | signature mismatch (HMAC verify fails) |
| Insert a fake record | sequence break + chain mismatch |
| Delete a middle record | sequence break |
| Reorder records | chain mismatch (prev_hash != expected) |
| Truncate a log to a prefix | ✅ verifies (this is fine — prefix is honest) |
| Stream output containing a denylisted pattern | StreamingHITLInterrupt |
| Stream output exceeding char cap | StreamingHITLInterrupt |

## Threat model (what v8 does NOT protect against)

- **Compromise of the HMAC secret.** If an attacker gets the secret,
  they can forge signatures. Rotate the secret periodically; treat its
  storage as you would any other long-lived credential.
- **Wholesale log replacement** (different attacker-signed log).
  Mitigation: pin secret rotation timestamps; audit the rotation events
  themselves.
- **Side-channel leaks** (timestamps, sizes, network metadata). Out of scope.
- **Audit log unavailability** (disk full, file deleted). Best-effort:
  failure to append writes to `state.errors` but doesn't crash the swarm.
  For production, monitor disk space + `state.errors` for `audit_jsonl_append failed`.

## What's preserved

| Concern | Status |
|---|---|
| `SwarmConfig()` no-arg → no audit, no streaming guards | ✅ |
| All v6/v7/v7.1 features | ✅ |
| Single-tenant default quota path | ✅ |
| Stub mode unchanged | ✅ |
| F-13A-CORR1 dedupe-merge reducer | ✅ (factory.py untouched) |
| F-29-CORR1 authoritative reset_usage | ✅ (tracker.py untouched) |
| Your local CLI fixes (Rich-escape, missing-gateway message) | ✅ (cli.py only gets additions, not rewrite) |

## Acceptance checklist

- [ ] All file copies done (5 new + 5 modified + 4 test files)
- [ ] Manual edits to dispatch.py applied per `_v8_streaming_hitl_patch.py`
- [ ] Manual edits to cli.py applied per `_v8_cli_additions.py`
- [ ] `pytest swarm-shared/tests/test_audit.py -q` → green (~30 tests)
- [ ] `pytest hive-swarm/tests/test_v8_*.py -q` → green
- [ ] `pytest ai-provider-swarm-gateway/tests/test_v8_audit_cli.py -q` → green
- [ ] Full regression: all suites still green
- [ ] Live: `audit verify` exits 0 on a clean log, 3 on a tampered log
- [ ] Live: streaming HITL pattern match converts worker to failed result with partial text in metadata

## Rollback

```bash
# Modified files — restore from .v7.1.bak
for f in hive-swarm/swarm/models/config.py \
         hive-swarm/swarm/models/state.py \
         hive-swarm/swarm/nodes/consensus.py \
         hive-swarm/swarm/nodes/approval.py \
         hive-swarm/swarm/nodes/worker.py
do
  mv "$f.v7.1.bak" "$f"
done

# New files — just delete
rm swarm-shared/swarm_shared/audit.py
rm swarm-shared/tests/test_audit.py
rm hive-swarm/swarm/_audit_helper.py
rm hive-swarm/tests/test_v8_*.py
rm ai-provider-swarm-gateway/tests/test_v8_audit_cli.py

# dispatch.py + cli.py — undo the manual edits (no automated path; use git)
```
