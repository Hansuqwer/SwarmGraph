"""Coverage guard test (F-04A).

Asserts BaseRedactingCheckpointer overrides EVERY abstract method of
BaseCheckpointSaver. If LangGraph 0.4 adds a new abstract method, this
test fails at PR time instead of silently leaking unredacted writes.
"""

import pytest

try:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

from swarm_shared.checkpointing import BaseRedactingCheckpointer


@pytest.mark.skipif(not HAS_LANGGRAPH, reason="langgraph not installed")
def test_redacting_checkpointer_covers_all_abstract_methods():
    """F-04A: assert every abstract method on BaseCheckpointSaver is implemented."""
    abstract = set(getattr(BaseCheckpointSaver, "__abstractmethods__", set()))
    implemented = set()
    for name in abstract:
        # Walk the MRO to find a concrete impl in BaseRedactingCheckpointer (or parent)
        for klass in BaseRedactingCheckpointer.__mro__:
            if name in klass.__dict__:
                if klass is not BaseCheckpointSaver:
                    implemented.add(name)
                break
    missing = abstract - implemented
    assert not missing, (
        f"BaseRedactingCheckpointer missing redaction overrides for: {missing}. "
        f"This means LangGraph added a new abstract write method since the last "
        f"swarm-shared release; add explicit overrides immediately."
    )


def test_redacting_checkpointer_imports_without_langgraph():
    """The class is importable even when langgraph is absent."""
    assert BaseRedactingCheckpointer is not None


@pytest.mark.skipif(not HAS_LANGGRAPH, reason="langgraph not installed")
def test_redacting_checkpointer_has_redaction_count():
    """Observability hook (F-20-OBS1)."""
    from langgraph.checkpoint.memory import InMemorySaver

    cp = BaseRedactingCheckpointer(InMemorySaver())
    assert cp.redaction_count == 0
