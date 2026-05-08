# Agent 29 — Provider Adapter & Quota Auditor
**Model:** Claude Opus 4.7
**Scope:** `ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/*.py`, `quota/tracker.py`, `registry/loader.py`, `providers.yaml`

## PURPOSE
Every adapter implements `ProviderAdapter` ABC fully; auth via env-var ref only (no hard-coded keys); quota tracker append-only; YAML schema validation.

## EVIDENCE BASE FETCHED
- `quota/tracker.py` (full)
- `graph/nodes.py` (full)
- Adapter list (from directory listing): `anthropic`, `openai`, `google`, `groq`, `deepseek`, `glm`, `kimi`, `mock`, `openrouter`, `qwen`, `base`.
- `base.py`, individual adapters, `loader.py`, `providers.yaml` — **NOT** fetched in this run.

## WHAT WORKS ✅ (verified in fetched files)

### `quota/tracker.py`
- `_DEFAULT_STORAGE = Path.home() / ".ai_provider_gateway" / "usage.json"` (`tracker.py:L13`) ✅.
- `_load` handles `JSONDecodeError` and `OSError` cleanly (`tracker.py:L26-L31`).
- `increment(requests, tokens)` raises if values are negative (`tracker.py:L65-L67`) ✅ — append-only enforced.
- `is_exhausted` returns `False` for unknown limits (`tracker.py:L87-L88`) — conservative.
- `_maybe_reset` correctly handles UTC timezone awareness (`tracker.py:L107-L116`) ✅.

### `graph/nodes.py`
- `_get_adapter(provider_id)` returns `MockAdapter()` as fallback for unknown providers (`graph/nodes.py:L65`) — fail-safe ✅.
- `provider_filter_node` checks both `provider.is_local` AND `adapter.is_configured()` (`graph/nodes.py:L138`) ✅.
- `quota_check_node` parses `req/day` from registry string and removes exhausted providers (`graph/nodes.py:L177-L195`) ✅.
- `swarm_route_node` scoring rewards: confirmed free API (+0.3), local provider (+0.2), verified confidence (+0.1), user-preferred (+0.5) — explicit and auditable (`graph/nodes.py:L209-L237`).
- `intake_node` rejects empty prompts and flags via `is_safe_to_proceed` (`graph/nodes.py:L84-L92`) ✅.

## WHAT'S BROKEN 🔴

### 29-CORR1 (critical) — `QuotaTracker._save` is NOT atomic
`tracker.py:L33-L37`:
```python
def _save(self) -> None:
    self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    self.storage_path.write_text(
        json.dumps(self._data, indent=2, default=str),
        encoding="utf-8",
    )
```
`Path.write_text` is **not atomic**. A crash mid-write produces a corrupt JSON file → next `_load` swallows the error and resets all quotas to 0 → over-counted "available" budget → user-visible quota overrun.

Fix: same tempfile + `os.replace` pattern as `FileCheckpointStore.save` (`hive-swarm/swarm/nodes/checkpointing.py:L73-L91`).

### 29-CORR2 (critical) — `QuotaTracker` has NO concurrency guard
Two processes (or async tasks) writing to the same `usage.json` will race:
1. Process A reads `{requests: 10}`.
2. Process B reads `{requests: 10}`.
3. A writes `{requests: 11}`.
4. B writes `{requests: 11}` — **lost increment**.

Result: under-counting of usage. Fix: file-locking (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) OR move to SQLite which has atomic transactions for free.

### 29-LG1 (high) — `_quota_tracker` is a module-level singleton initialised at import
`graph/nodes.py:L31`: `_quota_tracker = QuotaTracker()`. Created once per Python process, with the default storage path. Test isolation breaks: tests cannot inject a temporary `usage.json` without monkeypatching the module-level binding. Make `QuotaTracker` injectable via `GatewayState` or constructor parameter.

### 29-CORR3 (high) — `swarm_route_node` writes votes into `s.audit_log` as a JSON string with `__votes__:` prefix
`graph/nodes.py:L237-L240`:
```python
import json
s.log(f"swarm_route_node: votes={json.dumps(votes)}")
s.audit_log = s.audit_log + ["__votes__:" + json.dumps(votes)]
```
This **smuggles structured data through a string log**. `consensus_node` (next in chain — not fetched) presumably parses `audit_log[-1]` for the `__votes__:` prefix. That's a fragile sidechannel. Use a typed field on `GatewayState`:
```python
provider_votes: list[ProviderVote] = Field(default_factory=list, max_length=22)
```

### 29-CORR4 (high) — Adapter dict in `_get_adapter` instantiates ALL adapter classes on every call
`graph/nodes.py:L46-L65`. Every call constructs 10 adapter instances, then returns one. Each constructor likely does `os.environ.get(...)` — cheap but not free. Cache:
```python
_ADAPTER_CACHE: dict[str, ProviderAdapter] = {}
def _get_adapter(provider_id):
    if provider_id not in _ADAPTER_CACHE:
        # build the right one
        _ADAPTER_CACHE[provider_id] = _build_adapter(provider_id)
    return _ADAPTER_CACHE[provider_id]
```

### 29-DOC1 (med) — Per-provider adapter conformance not verifiable from this run
We did not fetch the individual `*_adapter.py` files. **Recommend Agent 29 re-runs against**:
- `providers/base.py` (the ABC)
- `providers/anthropic_adapter.py` (most relevant for May 2026 — must support `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5`)
- `providers/openai_adapter.py`
- `providers/openrouter_adapter.py`
- `providers/kimi_adapter.py`, `qwen_adapter.py`, `glm_adapter.py`, `deepseek_adapter.py` (newer adapters most likely to drift)

For each, confirm: (a) `is_configured()` reads only env-var name, never embeds key; (b) `__init__` does not log credentials; (c) all `ProviderAdapter` ABC methods are implemented.

### 29-CORR5 (med) — `quota_check_node` parses `req/day` via `daily_str.split()[0]`
`graph/nodes.py:L188-L193`. Brittle: requires the YAML to write `"100,000 req/day"` — comma-stripped via `.replace(",", "")`. A YAML edit to `"unlimited"` or `"100k req/day"` silently disables quota checking. Use a typed `int | None` field in `ProviderQuota`.

### 29-PERF1 (low) — `_load` runs synchronously on every QuotaTracker instantiation
File I/O on import. With a big `usage.json` (multi-MB after months of usage), startup latency spikes. Lazy-load on first `get_usage` call.

## WHAT'S MISSING 🟡
- No `httpx.AsyncClient` connection pooling visible in fetched code (each adapter call may rebuild TCP).
- No retry / backoff strategy in adapters (per-adapter; not in this fetch).
- No circuit breaker (health-check field in `swarm_route_node` is documented as "simplified — no real health check").
- No rate-limit headers parsed from provider responses (would update `usage.json` more accurately).
- No structured `ProviderVote` model — currently a dict.

## FIX RECOMMENDATION
```python
# tracker.py — atomic write + flock
import os, tempfile, fcntl

def _save(self) -> None:
    self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    serialised = json.dumps(self._data, indent=2, default=str)
    fd, tmp = tempfile.mkstemp(dir=str(self.storage_path.parent), prefix=".usage.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            fh.write(serialised)
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        os.replace(tmp, str(self.storage_path))
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 29-CORR1 non-atomic write | **critical** | 1h |
| 29-CORR2 no concurrency guard | **critical** | 1d (or 1h flock) |
| 29-LG1 singleton tracker | high | 30m |
| 29-CORR3 votes via string log | high | 30m |
| 29-CORR4 adapter rebuild per call | med | 15m |
| 29-DOC1 adapter re-audit | high | 1h (re-fetch + read) |
| 29-CORR5 brittle YAML parse | med | 30m |
| 29-PERF1 sync I/O on import | low | 30m |
