# Agent 12 — Memory & SONA Model Auditor
**Model:** Claude Opus 4.6
**Scope:** `hive-swarm/swarm/models/memory.py`; `ai-coder-hardening-improved/.../memory/lesson.py`

## PURPOSE
Validators (path traversal, shell-meta regex completeness incl. `! () {} \n \r`), EWC++ score promotion, vector adapter contract. **Cross-ref C4** from `ANALYSIS_AND_REVIEW.md`.

## PUBLIC SURFACE (verified)
- `class SwarmMemoryEntry(FrozenModel)` — 8 fields.
- `class SwarmMemory(HardenedModel)` — bounded store with `store/get/search/distill/promote_score`.
- `class VectorMemoryAdapter` — pluggable embedding stub.
- `class HybridMemorySearch` — vector-or-fallback search.
- `class MemoLesson(BaseModel)` — `extra='forbid', frozen=True` with strict validators.

## WHAT WORKS ✅

### `SwarmMemory` (`hive-swarm/.../memory.py`)
- `SwarmMemoryEntry` is `FrozenModel` ✅ — entries immutable (`memory.py:L21`).
- Field bounds: `key 1-256`, `value 1-8192`, `namespace 1-64`, `score ∈ [0,1]`, `access_count ge=0` (`memory.py:L22-L29`).
- `_rebuild_index` model_validator maintains a `namespace → key → entry` dict for O(1) lookup (`memory.py:L60-L65`) ✅.
- `store()` correctly de-dupes: removes old entry with same `(key, namespace)` before appending (`memory.py:L80-L85`) ✅.
- `_cap()` evicts lowest-score entries first (`memory.py:L195-L200`) ✅ — score-aware eviction.
- `distill()` removes entries below `sona_min_score` and returns the removed list for logging (`memory.py:L116-L130`) ✅ — clean SONA DISTILL implementation.
- `promote_score()` correctly clamps at 1.0 (`memory.py:L141-L150`) ✅.
- `HybridMemorySearch` falls back to keyword search when adapter raises `NotImplementedError` (`memory.py:L186-L192`) ✅.

### `MemoLesson` (`ai-coder-hardening-improved/.../lesson.py`)
- **C4 confirmed fixed**: `_SHELL_METACHAR_PATTERN` covers `; & | < > \\ \` $ ! ( ) { } \n \r * ? ^ ~` (`lesson.py:L26-L29`) ✅ — fully addresses the original gap.
- Added `_SAFE_GLOB_PATTERN` allowlist for `file_glob` (`lesson.py:L36-L39`) ✅.
- `MemoLesson` is `extra='forbid', frozen=True` (`lesson.py:L57-L60`) ✅.
- `_review_must_have_passed` enforces "only approved runs may store lessons" (`lesson.py:L99-L103`) ✅.
- `unsafe_summary_examples()` ships a CI-ready denylist verification dataset (`lesson.py:L113-L130`) ✅ — strong testing posture.

## WHAT'S BROKEN 🔴

### 12-CORR1 (high) — `SwarmMemory._index` is a class-level mutable default
`memory.py:L57`:
```python
_index: dict[str, dict[str, SwarmMemoryEntry]] = {}
```
This is the classic Python class-attribute mutable-default trap — **shared across all instances** of `SwarmMemory` if a future change initialises it as a class attribute rather than per-instance. Currently the `_rebuild_index` model_validator overwrites it via `object.__setattr__`, so each instance gets its own dict ✅, but the **declared type** `_index: dict[...] = {}` is misleading. Convert to `Field(default_factory=dict)` or a `PrivateAttr`.

### 12-LG1 (high) — `_index` is a private attribute but **not declared** as `PrivateAttr`
With `extra='forbid'`, Pydantic should reject unknown fields. `_index` is treated as a regular field because it has a leading underscore but no `PrivateAttr` declaration. Also: it's a `dict[str, dict[str, SwarmMemoryEntry]]` containing `FrozenModel` instances — these may not be JSON-serialisable through `model_dump(mode='json')` correctly without the `@field_serializer` decorator. **Test**: `swarm.memory.model_dump(mode='json')` may include `_index` as a key. Quick fix:
```python
from pydantic import PrivateAttr
_index: dict[str, dict[str, SwarmMemoryEntry]] = PrivateAttr(default_factory=dict)
```

### 12-CORR2 (med) — `search()` weights by `entry.score` BUT `score` is also part of `total` denominator
`memory.py:L100-L113`:
```python
sim = overlap / total if total > 0 else 0.0
weighted = sim * entry.score
```
The similarity uses Jaccard (`overlap / |query ∪ value ∪ key|`), then multiplies by `entry.score`. So an entry with `score=0.5` always loses to one with `score=1.0` even if Jaccard is 2x worse. Documented behaviour, but the multiplicative weighting is aggressive — log-weighted (`weighted = sim * (0.5 + 0.5 * entry.score)`) would be more forgiving.

### 12-CORR3 (med) — `distill()` deletes entries permanently with no archival hook
`memory.py:L122-L130`. Returns the removed entries but has no callback to archive them. EWC++ in the literature avoids "catastrophic forgetting"; an aggressive `sona_min_score=0.7` with `distill()` called every cycle will forget patterns that briefly dipped below 0.7 (e.g. via `promote_score(delta=-...)` if anyone adds that). Recommend an `on_distill: Callable | None = None` hook.

### 12-T1 (low) — `SwarmMemory.entries: list[SwarmMemoryEntry]` is unbounded by validator
`memory.py:L52`. Bounded only by `_cap()` at write time. A user constructing a `SwarmMemory` with `entries=[...10000...]` directly passes the constructor without `_cap()` running until a subsequent `store()`. Add a `model_validator(mode="after")` that calls `self._cap()`.

### 12-CORR4 (low) — `VectorMemoryAdapter.search_vectors` raises `NotImplementedError` but `embed()` returns `[]`
`memory.py:L171-L181`. The default contract is: `embed()→[]` triggers fallback. But a subclass that overrides only `embed()` (and forgets `search_vectors`) will hit `NotImplementedError`. The `HybridMemorySearch.search()` correctly catches this ✅. So this is fine — just ensure the docstring documents it.

### 12-CORR5 (low) — `MemoLesson.summary max_length=280` is a tweet-length convention with no rationale
`lesson.py:L67`. Why 280? Twitter is dead. Document as "summary is a one-line lesson; longer narrative → use the patch description instead" or pick a less culturally-loaded number (e.g. 256, 512).

## WHAT'S MISSING 🟡
- `SwarmMemory.export_jsonl()` / `import_jsonl()` for persistence between runs.
- `MemoLesson` has no `tags: list[str]` for filtered retrieval.
- No `SwarmMemory.merge(other)` for cross-swarm memory sharing.
- No interop layer between `MemoLesson` (ai-coder) and `SwarmMemoryEntry` (hive-swarm) — see Workflow W6 in `traces/`.

## FIX RECOMMENDATION
```python
# memory.py — diff
from pydantic import PrivateAttr

class SwarmMemory(HardenedModel):
    entries: list[SwarmMemoryEntry] = Field(default_factory=list)
    max_entries: int = Field(default=_MAX_ENTRIES, ge=10, le=100_000)
    sona_min_score: float = Field(default=0.7, ge=0.0, le=1.0)
    _index: dict[str, dict[str, SwarmMemoryEntry]] = PrivateAttr(default_factory=dict)  # ← fix

    @model_validator(mode="after")
    def _initial_cap(self) -> "SwarmMemory":
        self._cap()
        return self
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 12-CORR1 / 12-LG1 _index as PrivateAttr | high | 15m |
| 12-CORR2 search weighting docs | low | 10m |
| 12-CORR3 archive hook | med | 1h |
| 12-T1 initial cap | low | 5m |
| 12-CORR4 vector docstring | low | 5m |
| Missing JSONL persistence | high | 1d |

**Verdict on C4 from `ANALYSIS_AND_REVIEW.md`:** ✅ Fully fixed. The expanded denylist (`! ( ) { } \n \r * ? ^ ~`) is verified at `lesson.py:L26-L29`.
