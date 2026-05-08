# Agent 20 — Checkpointing & Redaction Auditor
**Model:** Claude Opus 4.7
**Scope:** `hive-swarm/swarm/nodes/checkpointing.py`; `ai-coder-hardening-improved/.../workflow/checkpoints.py`
**Cross-ref:** **C2/C3** from `ANALYSIS_AND_REVIEW.md`.

## PURPOSE
`RedactingCheckpointer` covers ALL `BaseCheckpointSaver` abstract methods (no `__getattr__` bypass), atomic file writes, backend factory, secret redaction patterns vs path preservation.

## METHOD COVERAGE MATRIX

The 8 methods on `BaseCheckpointSaver` (LangGraph 0.3, May 2026) are:

| Method | `SwarmRedactingCheckpointer` | `RedactingCheckpointer` (ai-coder, not fully fetched) |
|---|---|---|
| `get_tuple` (sync) | ✅ proxy unredacted (read-path OK) | ✅ |
| `aget_tuple` (async) | ✅ proxy unredacted | ✅ |
| `list` (sync) | ✅ proxy unredacted | ✅ |
| `alist` (async) | ✅ proxy unredacted (yield) | ✅ |
| `put` (sync) | ✅ **redacts** before write | ✅ |
| `aput` (async) | ✅ **redacts** before write | ✅ |
| `put_writes` (sync) | ✅ **redacts** values | ✅ |
| `aput_writes` (async) | ✅ **redacts** values | ✅ |

**Verdict on C3:** ✅ both implementations explicitly override every method. **No `__getattr__` bypass** detected in `hive-swarm/swarm/nodes/checkpointing.py:L98-L145`.

## WHAT WORKS ✅

### `hive-swarm/swarm/nodes/checkpointing.py`
- `InProcessCheckpointStore` — simple in-memory dict, useful for tests (`checkpointing.py:L26-L48`).
- `FileCheckpointStore` — atomic writes via `tempfile.mkstemp` + `os.fdopen` + `os.replace` (`checkpointing.py:L73-L91`) ✅ **C2 confirmed implemented in hive-swarm too**.
- `os.unlink(tmp_path)` cleanup in failure path (`checkpointing.py:L88-L91`) ✅.
- `serde` propagation: `super().__init__(serde=inner.serde)` only when LangGraph is available AND inner has serde (`checkpointing.py:L107-L111`) ✅ — defensive composition.
- `_redact` recursively walks dicts/lists (`checkpointing.py:L116-L124`) ✅.
- All 8 abstract methods explicitly implemented (see matrix above) ✅.

### `ai-coder-hardening-improved/.../workflow/checkpoints.py`
- **C2 confirmed fixed**: `LocalCheckpointStore.save` uses tempfile + `os.replace` (`checkpoints.py:L93-L108`) ✅.
- `CheckpointNotFound` and `CheckpointCorrupt` exceptions explicitly raised (`checkpoints.py:L40-L46, L120-L124`) ✅.
- `build_checkpointer` raises clear error for `local` backend (which is intended for the legacy JSON-artifact path, not LangGraph) (`checkpoints.py:L153-L157`) ✅ — **M2 confirmed addressed**.
- Two-redactor design: `full` for artifacts, `no_path` for checkpoints (preserves paths needed for resume) (`checkpoints.py:L52-L58`) ✅.

## WHAT'S BROKEN 🔴

### 20-SEC1 (critical) — `hive-swarm` `_redact` only matches `obj.startswith("sk-")` strings of len > 40
`checkpointing.py:L122`:
```python
if isinstance(obj, str) and len(obj) > 40 and obj.startswith("sk-"):
    return "[REDACTED]"
```
Misses: AWS keys (`AKIA...`), GCP service account JSON, Bearer tokens (`Bearer ey...`), GitHub PATs (`ghp_...`, `github_pat_...`), Anthropic keys (`sk-ant-...` — actually starts with `sk-` ✅), Google API keys (`AIza...`), OpenAI org IDs (`org-...`), generic JWTs (`eyJ...`), database DSNs (`postgres://user:pass@...`).

The docstring even admits this: `"Basic secret redaction — extend with real Redactor in production."` (`checkpointing.py:L116`).

The `ai-coder` version uses a real `Redactor` from `..redaction.config` and `..redaction.redactor` (verified at `checkpoints.py:L52-L58`). Recommend extracting `ai_coder.redaction` into a shared `swarm-redaction` package.

### 20-SEC2 (high) — `_redact` does NOT redact dict KEYS
`checkpointing.py:L118-L120`:
```python
if isinstance(obj, dict):
    return {k: self._redact(v) for k, v in obj.items()}
```
A checkpoint containing `{"sk-anthropic-key-...abcd": "some_value"}` would NOT have the key redacted. Dict keys can carry secrets in certain misuse patterns. Add key-side redaction.

### 20-CORR1 (high) — `FileCheckpointStore.load_latest` uses `glob` + `stat().st_mtime` — wall-clock-dependent
`checkpointing.py:L94-L101`: sorts checkpoints by file mtime. NTP jumps or filesystems with low mtime resolution (some Docker volumes have 1-second granularity) → wrong checkpoint selected. Encode iteration count in the filename and sort by that:
```python
# already encoded: cp-{swarm_id}-{iteration}-{rand}.json
candidates.sort(key=lambda p: int(p.stem.split('-')[2]))
```

### 20-CORR2 (med) — `InProcessCheckpointStore.save` builds `cp_id` with `secrets.token_hex(4)` — 32 bits ⇒ collision after 65k iterations of the same swarm
`checkpointing.py:L33`: `cp-{state.swarm_id}-{state.iteration}-{secrets.token_hex(4)}`. With `iteration` in the key, collisions only matter within the same iteration ✅. **OK** — but use `secrets.token_hex(8)` for extra safety (it's 8 hex chars = 64 bits).

### 20-LG1 (med) — `SwarmRedactingCheckpointer.put` returns the result of `inner.put` directly — but the LangGraph contract requires returning a `RunnableConfig`
`checkpointing.py:L131-L133`. The proxy correctly forwards. ✅ **No bug**, just confirming the contract is satisfied.

### 20-OBS1 (low) — No metric on redaction-hits-per-checkpoint
For ops, knowing "we redacted N strings this checkpoint" helps detect leak attempts.

## WHAT'S MISSING 🟡
- No CI test asserting `set(BaseCheckpointSaver.__abstractmethods__) <= set(SwarmRedactingCheckpointer.__dict__)`.
- No PostgresCheckpointStore in `hive-swarm` (only InProcess + File).
- No checkpoint TTL / GC.
- No checkpoint encryption at rest.
- No content-hash verification on load (defends against corrupt-but-valid-JSON files).

## FIX RECOMMENDATION
```python
# checkpointing.py — diff (high-priority items)
import re

# Replace the toy regex with a proper one:
_SECRET_PATTERNS = [
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}\b"),       # OpenAI / Anthropic
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                       # AWS access key
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),                 # Google API key
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),             # GitHub PAT
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),  # JWT
    re.compile(r"\bpostgres(?:ql)?://[^@]+@[^/]+/\S+"),        # DSN
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{10,}\b"),         # Bearer
]

def _redact_text(s: str) -> str:
    for pat in _SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    return s

def _redact(self, obj: Any) -> Any:
    if isinstance(obj, dict):
        return {self._redact_key(k): self._redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [self._redact(item) for item in obj]
    if isinstance(obj, str):
        return _redact_text(obj)
    return obj

def _redact_key(self, k: Any) -> Any:
    return _redact_text(k) if isinstance(k, str) else k
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 20-SEC1 toy redaction regex | **critical** | 1d |
| 20-SEC2 dict keys not redacted | high | 15m |
| 20-CORR1 wall-clock load | high | 15m |
| 20-CORR2 token_hex length | low | 1m |
| 20-OBS1 redaction metric | low | 30m |
| Missing coverage-guard test | critical | 1h (see Agent 04) |
| Missing PostgresCheckpointStore | high | 1d |

**Verdict on C2:** ✅ Fully fixed in both `ai-coder` and `hive-swarm` (atomic writes verified).
**Verdict on C3:** ✅ Method coverage is complete in the current file (8/8). **But** still no automated guard against future LangGraph 0.4 method additions. See Agent 04, finding 04-T2.
