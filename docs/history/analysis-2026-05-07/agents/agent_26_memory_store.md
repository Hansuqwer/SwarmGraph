# Agent 26 — Memory Store Auditor
**Model:** Claude Opus 4.6
**Scope:** `hive-swarm/swarm/models/memory.py::SwarmMemory`, `VectorMemoryAdapter`, `HybridMemorySearch`.

## PURPOSE
Capacity bounds, eviction policy, score-promotion math, persistence path safety.

## PUBLIC SURFACE (verified)
- `SwarmMemory.store(key, value, namespace, score, tags, source_agent_id)`
- `SwarmMemory.get(key, namespace) -> SwarmMemoryEntry | None`
- `SwarmMemory.search(query, namespace, top_k, min_score) -> list[SwarmMemoryEntry]`
- `SwarmMemory.distill() -> list[SwarmMemoryEntry]` (returns removed)
- `SwarmMemory.promote_score(key, namespace, delta=0.05)`
- `SwarmMemory.namespace_entries(namespace)`, `size()`
- `VectorMemoryAdapter.embed(text)`, `search_vectors(...)`
- `HybridMemorySearch.search(query, top_k, namespace)`

## WHAT WORKS ✅
- `_cap()` evicts lowest-score entries first (`memory.py:L195-L200`) — score-aware ✅.
- Namespace-keyed `_index` rebuilt after every mutation (`memory.py:L60-L65, L88-L89, L128-L130`) ✅.
- `store()` correctly de-dupes per `(key, namespace)` (`memory.py:L80-L85`) ✅.
- `distill()` returns removed entries for caller logging (`memory.py:L116-L130`) ✅.
- `HybridMemorySearch` graceful fallback to keyword when adapter raises NotImplemented (`memory.py:L186-L192`) ✅.

## WHAT'S BROKEN 🔴

### 26-LG1 (high) — `_index` declared as a regular field, not `PrivateAttr` — SAME as 12-LG1
`memory.py:L57`. Already flagged. Restated for blast-radius accounting.

### 26-CORR1 (high) — `_cap()` sorts entries IN-PLACE by score descending, scrambling insertion order
`memory.py:L197-L199`:
```python
self.entries.sort(key=lambda e: e.score, reverse=True)
self.entries = self.entries[: self.max_entries]
```
After eviction, the entries list is **score-sorted**, no longer insertion-sorted. Subsequent `search()` over the (now sorted) list will iterate score-descending — fine for keyword search ✅. But any consumer relying on `entries` being chronological breaks. Either:
- Sort a copy (preserve original order), or
- Document the ordering as score-descending post-eviction.

### 26-CORR2 (med) — `_cap()` is only called from `store()`; not called from `__init__` / construction
A `SwarmMemory(entries=[...10000...])` constructed directly bypasses `_cap()`. The `_rebuild_index` validator runs on every entry, but the cap doesn't enforce. Already flagged in 12-T1.

### 26-CORR3 (med) — `promote_score` re-stores the entry, which evicts and re-inserts → bumps `created_at` reset
`memory.py:L141-L150`. `self.store(key=existing.key, value=existing.value, ...)` creates a brand-new `SwarmMemoryEntry` with `created_at = now()`. The entry's age is reset to 0. If `created_at` is used for "age-based eviction" downstream, this corrupts metrics. Recommend a direct mutation path:
```python
def promote_score(self, key, namespace="default", delta=0.05):
    existing = self.get(key, namespace)
    if existing is None: return
    new_score = min(1.0, existing.score + delta)
    # Replace with score-bumped entry preserving created_at
    bumped = existing.model_copy(update={"score": new_score, "access_count": existing.access_count + 1})
    self.entries = [e for e in self.entries if not (e.key == key and e.namespace == namespace)] + [bumped]
    self._rebuild_index()
```

### 26-CORR4 (med) — `search()` pulls from `self.entries` then filters by namespace inline (O(N) per search)
`memory.py:L100-L113`. With `_index` already keyed by namespace, the search should be O(N_namespace) not O(N_total). Use `_index[namespace].values()` when namespace is set.

### 26-PERF1 (low) — `search()` allocates a new `tuple` and `set` per entry — ~10x faster with set comprehension if pre-tokenized
Sub-millisecond at memory_max_entries=1000; flagged for awareness.

### 26-CORR5 (low) — `VectorMemoryAdapter.embed()` returns `[]` by default — but the `HybridMemorySearch` checks `if embedding:`
`memory.py:L185-L186`. `[]` is falsy → fallback triggers ✅. But a subclass that returns `[0.0, 0.0, ...]` (all zeros, but non-empty list) would pass the check and then fail in `search_vectors`. Use `if embedding and any(embedding):`.

## WHAT'S MISSING 🟡
- No persistence (`save_jsonl(path)` / `load_jsonl(path)`).
- No expiry (`expires_at` on entries, evict by date).
- No `merge(other_memory: SwarmMemory)` for cross-swarm transfer.
- No metric on `search` recall@k (would need ground truth).
- No mutex for multi-thread access (LangGraph workers run in parallel).

## FIX RECOMMENDATION
```python
# memory.py — diff
def search(self, query, *, namespace=None, top_k=5, min_score=0.0):
    query_tokens = set(query.lower().split())
    if namespace:
        candidates = self._index.get(namespace, {}).values()   # O(N_namespace)
    else:
        candidates = self.entries
    results = []
    for entry in candidates:
        if entry.score < min_score:
            continue
        value_tokens = set(entry.value.lower().split())
        key_tokens = set(entry.key.lower().replace("-", " ").split())
        union = query_tokens | value_tokens | key_tokens
        sim = len(query_tokens & (value_tokens | key_tokens)) / max(len(union), 1)
        results.append((sim * entry.score, entry))
    results.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in results[:top_k]]
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 26-LG1 _index PrivateAttr | high | 15m |
| 26-CORR1 sort-in-place | med | 15m |
| 26-CORR2 init not capped | low | 5m |
| 26-CORR3 created_at reset | med | 30m |
| 26-CORR4 namespace filter post-fetch | low | 15m |
| 26-CORR5 zero-vec passes truthy | low | 5m |
| Missing JSONL persistence | high | 1d |
| Missing thread mutex | high | 1d |
