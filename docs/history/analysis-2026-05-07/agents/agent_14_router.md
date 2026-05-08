# Agent 14 — Router Auditor
**Model:** Claude Sonnet 4.6
**Scope:** `hive-swarm/swarm/nodes/router.py`

## PURPOSE
Verify 3-tier thresholds, fall-through, and the topology dispatch matrix.

## PUBLIC SURFACE (verified)
- `_COMPLEX_KEYWORDS`, `_SIMPLE_KEYWORDS` — heuristics
- `estimate_complexity(task_description: str) -> float`
- `_TOPOLOGY_QUEEN_NODE: dict[SwarmTopology, str]` (5 entries)
- `route_task(state: dict) -> str` (conditional-edge function)
- `router_node(state: dict) -> dict` (writes complexity + tier into state)

## TOPOLOGY × TIER MATRIX

| Topology \ Tier | tier1_fast | tier2_medium | tier3_swarm |
|---|---|---|---|
| hierarchical | fast_agent ✅ | medium_agent ✅ | hierarchical_queen ✅ |
| mesh | fast_agent ✅ | medium_agent ✅ | mesh_queen ✅ |
| ring | fast_agent ✅ | medium_agent ✅ | ring_queen ✅ |
| star | fast_agent ✅ | medium_agent ✅ | star_queen ✅ |
| adaptive | fast_agent ✅ | medium_agent ✅ | adaptive_queen ✅ |

→ Full coverage. ✅

## WHAT WORKS ✅
- Heuristic clamps to `[0, 1]` (`router.py:L52`).
- Tier dispatch via `swarm.config.complexity_tier(score)` correctly delegates threshold logic to `SwarmConfig` (`router.py:L84`) — single source of truth.
- Topology fall-through to `"hierarchical_queen"` if unknown topology (`router.py:L92`) ✅ — defensive default.
- `router_node` updates `complexity_score`, `complexity_tier`, status, history, and timestamp atomically before returning the JSON dict (`router.py:L99-L113`) ✅.

## WHAT'S BROKEN 🔴

### 14-CORR1 (high) — `_COMPLEX_KEYWORDS` includes substrings that produce false-positives
`router.py:L17-L23`:
```python
"orchestrat", "consensus", "implement", "build",
"create system", "entire", "comprehensive", "full",
```
- `"build"` matches the verb in *literally any* coding task → forces tier 3.
- `"implement"` matches every coding task → forces tier 3.
- `"comprehensive"` matches benign descriptions ("comprehensive docstring") → tier 3.

Result: in production, **almost every task** scores tier-3, defeating the cost-saving rationale of Tier 1/2.

### 14-CORR2 (med) — `_SIMPLE_KEYWORDS` includes phrases that often appear inside complex tasks
`router.py:L25-L28`: `"add type hint"`, `"add import"`. A task description like "rebuild the auth module and **add type hints** throughout" gets a `simple_hits=1` deduction → bumps complexity score *down*. Bad classifier.

### 14-CORR3 (med) — `length_score = min(word_count / 200.0, 0.5)` caps at 0.5 → tier 1+2 are accessible only via missing keywords
With a 200-word objective, `length_score=0.5` → already tier 3 (default `tier2_threshold=0.50`). To land in tier 2, you need either `keyword_score < 0` (i.e. simple_hits > 0) or `< 200` words — combined with `word_count / 200`. Net effect: tier 1 requires extremely short, simple-keyword-heavy text. The router **strongly biases to tier 3** in real usage.

### 14-CORR4 (med) — No tokenization handles punctuation/case; `"!"` keyword `"orchestrat"` matches inside `"reorchestrate"` → false positive
Plain `in text` substring match; `"orchestrat"` matches `"reorchestrating"` ✅ (intended). But `"async"` matches inside `"asynchrony"` (intended) AND inside `"asynchronously"` (still intended). However `"const"` (in `_SIMPLE_KEYWORDS`) matches `"constraint"` (NOT intended) and `"constant"`. Use word-boundary regex.

### 14-T1 (low) — `route_task` re-validates `SwarmState` from dict on **every** routing decision
`router.py:L82`: `swarm = SwarmState.model_validate(state)`. With `validate_assignment=True` and ~8 fields touched, this is full revalidation (28 fields) per routing. For a Tier-3 retry loop hitting `route_task` 10 times, that's 10 full revalidations. At swarm scale this is fine; flagged for awareness.

### 14-OBS1 (low) — `router_node` appends history with `kind="swarm_init"` even on retries
`router.py:L107`. `kind="swarm_init"` is misleading on retry. Should be `kind="task_assigned"` or a new `kind="route"`.

## WHAT'S MISSING 🟡
- No LLM-based complexity classifier (Tier-2 single-call could classify the next task).
- No telemetry on tier-distribution (would help tune thresholds).
- No ablation: `swarm.config.tier1_threshold = 0.0` should disable Tier 1; not tested.

## FIX RECOMMENDATION
```python
# router.py — diff
import re

_COMPLEX_PATTERNS = [
    re.compile(r"\barchitecture\b", re.I),
    re.compile(r"\bdesign\b", re.I),
    re.compile(r"\bdistributed\b", re.I),
    # ... (word-boundary, case-insensitive)
]
_SIMPLE_PATTERNS = [
    re.compile(r"\brename\b", re.I),
    re.compile(r"\btypo\b", re.I),
    # ...
]

def estimate_complexity(task_description: str) -> float:
    text = task_description
    word_count = len(text.split())
    simple_hits = sum(1 for p in _SIMPLE_PATTERNS if p.search(text))
    complex_hits = sum(1 for p in _COMPLEX_PATTERNS if p.search(text))
    length_score = min(word_count / 400.0, 0.4)   # raise denominator
    keyword_score = (complex_hits * 0.10) - (simple_hits * 0.10)
    return round(max(0.0, min(1.0, length_score + keyword_score)), 3)

# add `kind="route"` to HistoryKind in types.py and use it here
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 14-CORR1 keyword false-positives | high | 30m |
| 14-CORR2 deduction inside complex | med | 30m |
| 14-CORR3 length cap forces tier3 | med | 30m |
| 14-CORR4 substring match | med | 1h |
| 14-T1 revalidation cost | low | n/a (acceptable) |
| 14-OBS1 misleading history kind | low | 5m |
