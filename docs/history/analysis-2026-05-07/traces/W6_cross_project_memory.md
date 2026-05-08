# Workflow W6 — Cross-Project Memory Portability

**Question:** Can a `MemoLesson` from `ai-coder-hardening-improved` be ingested into `hive-swarm`'s `SwarmMemory`?

## Schema comparison

| Field | `MemoLesson` (ai-coder) | `SwarmMemoryEntry` (hive-swarm) |
|---|---|---|
| Identity | `(rule_kind: Literal[4], file_glob: str)` | `(key: str, namespace: str)` |
| Body | `summary: str (max 280)` | `value: str (max 8192)` |
| Score | `review_passed: bool` (always `True`) | `score: float ∈ [0,1]` |
| Created | `created_at: datetime` (UTC) | `created_at: float` (UNIX ts) |
| Tags | ❌ none | `tags: list[str]` |
| Source | ❌ none | `source_agent_id: str` |
| Access | ❌ none | `access_count: int` |
| Validators | shell-metachar denial, URL denial | none specific |

## Possible adapter

```python
# adapters/lesson_to_entry.py (proposed)
from datetime import datetime, timezone

def lesson_to_entry(lesson: MemoLesson, namespace: str = "ai_coder") -> SwarmMemoryEntry:
    """Convert ai-coder MemoLesson → hive-swarm SwarmMemoryEntry."""
    key = f"{lesson.rule_kind}:{lesson.file_glob}"
    return SwarmMemoryEntry(
        key=key[:256],                                    # cap to SwarmMemoryEntry.key max
        value=lesson.summary[:8192],                      # cap (already 280 from MemoLesson)
        namespace=namespace,
        score=1.0,                                        # MemoLesson.review_passed=True ⇒ trusted
        tags=["from_ai_coder", lesson.rule_kind],
        source_agent_id="ai_coder_review",
        # created_at: SwarmMemoryEntry uses time.time() default;
        # MemoLesson.created_at is datetime → must convert
    )
```

The **reverse direction** (hive-swarm → ai-coder) is harder because `SwarmMemoryEntry.value` can be 8192 chars but `MemoLesson.summary` caps at 280, AND `MemoLesson` has strict shell-metachar/URL validators that may reject `SwarmMemoryEntry.value` content (especially if it contains code with `;`, `|`, `>`, etc.).

## Should it be done?

| Argument for | Argument against |
|---|---|
| Both projects share Pydantic v2 + LangGraph stack | Different validation contracts (`MemoLesson` is restricted, `SwarmMemoryEntry` is permissive) |
| Both projects have `extra='forbid', frozen=True` discipline | Different score semantics (`bool` vs `float`) |
| `ai-coder` lessons are HIGH-quality (only-from-approved-runs) — useful for `hive-swarm` retrieval | `MemoLesson.summary` denies code snippets due to shell-metachar block — limits cross-flow |
| Cross-pollination would close the SONA loop across the two projects | No shared package today; cross-import creates a coupling the projects clearly avoided |

## Recommendation

✅ **Add a one-way adapter** (`MemoLesson → SwarmMemoryEntry`) in a new shared package `swarm-shared` (already proposed for `RedactingCheckpointer`, atomic-write helper, hash helper).

❌ **Do not add the reverse direction** — cross-validation would silently drop most entries due to MemoLesson's strict denylist.

## Concrete shared package design (preview)

```
swarm-shared/
├── pyproject.toml              dependencies = ["pydantic>=2.7,<3"]
├── swarm_shared/
│   ├── __init__.py
│   ├── hashing.py              stable_hash(text, length=16)
│   ├── time.py                 now_ts(), monotonic_ts()
│   ├── bounded_list.py         CappedList typed wrapper
│   ├── atomic_write.py         atomic_write_json(path, data)
│   ├── redaction.py            SECRET_PATTERNS, redact_text, redact_obj
│   ├── checkpointing.py        BaseRedactingCheckpointer (one impl)
│   └── memory_adapters.py      lesson_to_entry, etc.
```

## Findings linked to W6
- **W6-MISSING-1 (high)** — no shared package; 3+ duplications across projects
- **W6-MISSING-2 (med)** — no `MemoLesson ↔ SwarmMemoryEntry` adapter
- **W6-DOC-1 (low)** — docs do not mention cross-project portability is intentional or accidental

## Cross-reference
See `docs/architecture_overview.md` "Cross-project consolidation opportunities" + `HIVE_ANALYSIS_REPORT.md` "Architectural recommendations".
