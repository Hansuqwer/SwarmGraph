# Patch note — ai-provider-swarm-gateway (2026-05-07)

## Files patched in this run

| File | Owner | Fix IDs | Summary |
|---|---|---|---|
| `src/ai_provider_swarm_gateway/quota/tracker.py` | A29 | F-29A, F-29B, F-29-PERF1, F-29-LG1 | Atomic write via `swarm_shared.atomic_write_json`; cross-platform `fcntl/msvcrt` file lock around read-modify-write; lazy load on first `get_usage`; injectable `storage_path` |

## Files NOT patched (deferred)

| Item | Reason |
|---|---|
| `graph/nodes.py:swarm_route_node` (F-29C — votes-via-string-log smuggling) | Requires `models/state.py` model edit to add `provider_votes: list[ProviderVote]`; that file was not fetched in the analysis run (RR1). Deferred to a follow-up patch with the re-fetch. |
| `graph/nodes.py:_get_adapter` adapter cache (F-29C) | Same reason: per-adapter ABC conformance needs `providers/*.py` re-fetch (RR4). |
| `dashboard/app.py`, `cli.py` re-audit (F-30B) | Files not in this workspace fetch (RR1). Deferred. |
| `models/state.py:user_prompt` cap (F-30A) | Requires the re-fetch above. Deferred. |
| `classify_request_node` substring match (F-30C) | Same reason. Deferred. |

## Cross-cutting

- `swarm-shared` package now provides `atomic_write_json` and `BaseRedactingCheckpointer`. The gateway's `tracker.py` is the first consumer; once `dashboard/` and `models/state.py` are re-fetched in a follow-up, the `BaseRedactingCheckpointer` can also replace any in-gateway redaction code.

## How to verify locally

```bash
cd swarmMain/ai-provider-swarm-gateway
pip install -e ../swarm-shared
pip install -e .[dev]
pytest tests -q
```

If tests fail because of the un-fetched files (`models/state.py` etc.), that is expected — the `quota/tracker.py` patch is independent and its own tests should pass.
