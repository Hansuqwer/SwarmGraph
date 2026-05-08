# 🐝 Patch v8 — Operational hardening (audit signing + streaming HITL)

## Mission

Ship two integrated hardening features:

### 1. Audit log signing (HMAC-SHA256 + chained hash)

Every consensus round, approval decision, and worker result gets a tamper-
evident HMAC-SHA256 signature. Records form a hash-chained log (each
record's `prev_hash` field references the previous record's full digest)
so any insertion / deletion / reordering breaks the chain.

Two modes:
- **In-process audit** (`SwarmConfig.audit_signing_enabled=True`):
  signed records appended to `SwarmState.audit_records: list[AuditRecord]`.
- **Persistent audit log** (`audit_log_path: Path | None`):
  signed records also flushed to a per-swarm append-only JSONL file via
  the existing `swarm_shared.atomic_write_json` pattern (line-by-line append).

Verification CLI:
```bash
ai-provider-gateway audit verify path/to/audit.jsonl --secret-env AUDIT_HMAC_KEY
```

### 2. Streaming HITL — interrupt mid-generation

When workers stream and the partial output trips a configured guard
(default: regex denylist + max-output cap), the dispatcher raises a
`StreamingHITLInterrupt`. The CLI presents the partial output + the
trigger reason and asks the operator to (a) abort, (b) continue, or
(c) accept-as-is.

Two trigger sources:
- **Pattern triggers** — `SwarmConfig.streaming_guard_patterns: list[str]`
  (regexes; default empty). Matches against accumulated `text` per chunk.
- **Length cap** — `SwarmConfig.streaming_max_output_chars: int = 16384`
  (per-worker output cap; abort beyond).

Single-use guard preserved (F-19A): the resume token issued for streaming
HITL is single-use just like the consensus HITL token.

## Hard rules

1. **Backwards compatible by default.** No-arg `SwarmConfig()` unchanged
   (audit_signing_enabled=False, no streaming guards).
2. **No new top-level deps.** HMAC via stdlib `hmac` + `hashlib`. Chunk
   guards via stdlib `re`.
3. **All errors typed.** `AuditChainBroken` / `StreamingHITLInterrupt`.
4. **Per-tenant friendly** — audit log path can include `{tenant}` placeholder.
5. **Anti-drift sentinel guards scope.** Pure additive; no graph rewrites.

## Hive Orchestrator role assignments (v8 dispatch)

| Agent | Layer | Owns |
|---|---|---|
| **A20** Checkpointing/Audit | C | `swarm_shared/audit.py` — AuditRecord, sign, verify, chain |
| **A07** Agent-Model | B | `swarm/models/agent.py` — AuditRecord wired into WorkerResult |
| **A09** State-Machine | B | `swarm/models/state.py` — `audit_records` field |
| **A10** Config | B | `swarm/models/config.py` — audit + streaming-HITL fields |
| **A17** Consensus Node | C | `swarm/nodes/consensus.py` — sign every consensus_result |
| **A19** Approval / HITL | C | `swarm/nodes/approval.py` — sign every approval_decision |
| **A16** Worker | C | `swarm/nodes/worker.py` — sign every worker_result |
| **A17b** Dispatcher | C | `swarm/llm/dispatch.py` — `StreamingHITLInterrupt` + per-chunk guards |
| **A30** Gateway CLI | F | `cli.py` — `audit verify` subcommand + streaming HITL prompt |
| **A04** Test-Strategy | A | regression tests per feature |
| **A05** Anti-Drift Sentinel | A | sign off; no scope creep |

## Deliverables (`cli_handover_patch_v8/`)

```
swarm-shared/
└── swarm_shared/
    └── audit.py                              ← NEW (AuditRecord, sign, verify, chain)
└── tests/
    └── test_audit.py                         ← NEW

hive-swarm/
├── swarm/
│   ├── models/
│   │   ├── agent.py                          ← MODIFIED (AuditRecord re-export, WorkerResult.signature)
│   │   ├── state.py                          ← MODIFIED (audit_records field)
│   │   └── config.py                         ← MODIFIED (8 audit + streaming fields)
│   ├── nodes/
│   │   ├── consensus.py                      ← MODIFIED (sign consensus_result)
│   │   ├── approval.py                       ← MODIFIED (sign approval_decision)
│   │   └── worker.py                         ← MODIFIED (sign worker_result)
│   └── llm/
│       └── dispatch.py                       ← MODIFIED (StreamingHITLInterrupt + guards)
└── tests/
    ├── test_v8_audit_signing.py              ← NEW
    └── test_v8_streaming_hitl.py             ← NEW

ai-provider-swarm-gateway/
├── src/ai_provider_swarm_gateway/
│   └── cli.py                                ← MODIFIED (audit verify subcommand + stream-HITL prompt)
└── tests/
    └── test_v8_audit_cli.py                  ← NEW

HIVE_V8_PROMPT.md                             ← this prompt
HANDOVER_PATCH_v8.md                          ← apply / verify / rollback / threat model
```

## Acceptance criteria

| # | Criterion |
|---|---|
| 1 | `pytest swarm-shared/tests/test_audit.py -q` → green |
| 2 | `pytest hive-swarm/tests/test_v8_*.py -q` → green |
| 3 | `pytest ai-provider-swarm-gateway/tests/test_v8_*.py -q` → green |
| 4 | Full regression: all suites still green |
| 5 | `ai-provider-gateway audit verify <log>` exits 0 on a clean log, non-zero on tampering |
| 6 | Inserting a fake record into a JSONL audit log breaks `verify` |
| 7 | Reordering records in the log breaks `verify` (chained hash catches this) |
| 8 | Deleting a record breaks `verify` |
| 9 | Streaming worker hits a `streaming_guard_patterns` match → raises `StreamingHITLInterrupt` mid-stream |
| 10 | Streaming HITL accept/abort/continue choice round-trips through CLI prompt |

## Stop signal

```
✅ V8 SHIPPED
   Audit log signing (HMAC-SHA256 + hash chain)
   Streaming HITL (per-chunk guards + interactive resume)
   `audit verify` CLI
   All test suites green
   Tamper-evidence: insertion/deletion/reorder all break verify
```

— end of prompt —
