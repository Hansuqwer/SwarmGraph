"""Cross-project memory adapters (F-W6A, W6 trace).

Currently: one-way ``MemoLesson → SwarmMemoryEntry`` adapter.
Reverse direction is intentionally NOT supported because MemoLesson's
strict shell-metachar denylist would silently reject most code-content
SwarmMemoryEntry values (see traces/W6_cross_project_memory.md).
"""
from __future__ import annotations

from typing import Any, Protocol


class _LessonLike(Protocol):
    rule_kind: str
    file_glob: str
    summary: str

    def key(self) -> tuple[str, str]: ...


def lesson_to_entry_dict(
    lesson: _LessonLike,
    *,
    namespace: str = "ai_coder",
    score: float = 1.0,
) -> dict[str, Any]:
    """Convert a MemoLesson-shaped object into a SwarmMemoryEntry-shaped dict.

    Returns a dict (not a SwarmMemoryEntry) to avoid forcing a hive-swarm
    import into the shared package. Caller passes the dict to
    ``SwarmMemoryEntry.model_validate(...)``.
    """
    key = f"{lesson.rule_kind}:{lesson.file_glob}"
    return {
        "key": key[:256],
        "value": lesson.summary[:8192],
        "namespace": namespace,
        "score": score,
        "tags": ["from_ai_coder", lesson.rule_kind],
        "source_agent_id": "ai_coder_review",
    }
