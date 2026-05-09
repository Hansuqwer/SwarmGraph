"""Regression tests for the 6 canonical fixes in v7.

Each test is named for its canonical fix ID so failures point straight at
the responsible patch.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from swarm.graphs.factory import _merge_worker_results
from swarm.llm.dispatch import (
    DEFAULT_SETTINGS,
    _env_bool,
    resolve_llm_settings,
)
from swarm.llm.embeddings import HashEmbedder, NullEmbedder
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState
from swarm.nodes.queen import _llm_settings_from_config

# ── F-13A-CORR1: dedupe-merge reducer for worker_results ────────────────


def test_merge_worker_results_idempotent_on_replay():
    """The 80-vs-5 fix: re-emitting the same WorkerResult dict must NOT
    duplicate the entry."""
    r1 = {"agent_id": "coder-1", "task_id": "task-1-1", "output": "v1"}
    r2 = {"agent_id": "tester-1", "task_id": "task-1-2", "output": "v2"}
    initial = [r1, r2]
    # Replay: LangGraph re-emits the same dicts during retry / checkpoint replay
    merged = _merge_worker_results(initial, [r1, r2])
    assert len(merged) == 2


def test_merge_worker_results_right_wins_on_collision():
    """When the same (agent_id, task_id) appears twice, the LATER entry wins."""
    old = {"agent_id": "coder-1", "task_id": "task-1-1", "output": "old"}
    new = {"agent_id": "coder-1", "task_id": "task-1-1", "output": "new"}
    merged = _merge_worker_results([old], [new])
    assert len(merged) == 1
    assert merged[0]["output"] == "new"


def test_merge_worker_results_distinct_keys_appended():
    """Distinct (agent_id, task_id) tuples → both kept."""
    a = {"agent_id": "coder-1", "task_id": "task-1-1", "output": "a"}
    b = {"agent_id": "coder-2", "task_id": "task-1-2", "output": "b"}
    merged = _merge_worker_results([a], [b])
    assert len(merged) == 2


def test_merge_worker_results_preserves_order():
    """First-seen position preserved across merge."""
    a = {"agent_id": "a", "task_id": "1", "output": "A"}
    b = {"agent_id": "b", "task_id": "2", "output": "B"}
    c = {"agent_id": "c", "task_id": "3", "output": "C"}
    merged = _merge_worker_results([a, b], [c, a])
    # Order: a (kept first), b, c (new)
    assert [m["agent_id"] for m in merged] == ["a", "b", "c"]


def test_merge_worker_results_handles_empty():
    assert _merge_worker_results(None, None) == []
    assert _merge_worker_results([], []) == []
    a = {"agent_id": "a", "task_id": "1", "output": "A"}
    assert _merge_worker_results([a], None) == [a]
    assert _merge_worker_results(None, [a]) == [a]


def test_merge_worker_results_tolerates_malformed():
    """Defensive: dicts missing agent_id/task_id are still merged via repr key."""
    weird = {"some_other_field": "value"}
    merged = _merge_worker_results([weird], [weird])
    assert len(merged) == 1  # de-duped via repr fallback


def test_no_more_iteration_storm_doubling():
    """Simulates 5 fan-outs replayed 16 times; result should be 5, not 80."""
    fanout = [
        {"agent_id": f"role-{i}", "task_id": f"t-1-{i}", "output": f"o-{i}"} for i in range(5)
    ]
    state = []
    for _ in range(16):  # 16 iterations
        state = _merge_worker_results(state, fanout)
    assert len(state) == 5  # NOT 80


# ── F-18-CORR2: threshold=0 coalesces to mode-off ──────────────────────


def _state(mode="keyword", threshold=0.4, enabled=True):
    cfg = SwarmConfig(
        anti_drift_enabled=enabled,
        anti_drift_mode=mode,
        anti_drift_similarity_threshold=threshold,
    )
    return SwarmState(swarm_id="s1", objective="implement OAuth refresh tokens", config=cfg)


def test_threshold_zero_in_keyword_mode_always_passes():
    """F-18-CORR2: threshold=0 in keyword mode always returns True."""
    s = _state(mode="keyword", threshold=0.0)
    assert s.check_drift("totally unrelated text") is True


def test_threshold_zero_in_embedding_mode_always_passes():
    """F-18-CORR2: threshold=0 in embedding mode coalesces to off."""
    s = _state(mode="embedding", threshold=0.0)
    assert s.check_drift("xyz", embedder=HashEmbedder()) is True


def test_threshold_zero_off_mode_passes_too():
    s = _state(mode="off", threshold=0.0)
    assert s.check_drift("anything") is True


def test_nonzero_threshold_still_works_in_keyword():
    """Sanity: F-18-CORR2 only applies when threshold == 0."""
    s = _state(mode="keyword", threshold=0.5)
    assert s.check_drift("def foo(): pass") is False  # zero overlap


# ── F-15-FWD1: queen forwards stream + cost ─────────────────────────────


def test_queen_forwards_stream_enabled_to_workers():
    cfg = SwarmConfig(llm_stream_enabled=True)
    settings = _llm_settings_from_config(cfg)
    assert settings["stream_enabled"] is True


def test_queen_forwards_cost_tracking_to_workers():
    cfg = SwarmConfig(cost_tracking_enabled=False)
    settings = _llm_settings_from_config(cfg)
    assert settings["cost_tracking_enabled"] is False


def test_queen_default_settings_match_back_compat():
    cfg = SwarmConfig()
    settings = _llm_settings_from_config(cfg)
    assert settings["stream_enabled"] is False
    assert settings["cost_tracking_enabled"] is True
    assert settings["backend"] == "stub"


# ── F-17-ENV1: HIVE_SWARM_COST_TRACKING env var ─────────────────────────


def test_env_bool_true_strings():
    for s in ("1", "true", "TRUE", "yes", "on"):
        os.environ["__TEST_ENV__"] = s
        assert _env_bool("__TEST_ENV__", False) is True
    os.environ.pop("__TEST_ENV__", None)


def test_env_bool_false_strings():
    for s in ("0", "false", "no", "off", ""):
        os.environ["__TEST_ENV__"] = s
        assert _env_bool("__TEST_ENV__", True) is False
    os.environ.pop("__TEST_ENV__", None)


def test_env_bool_unknown_returns_default():
    os.environ["__TEST_ENV__"] = "maybe"
    assert _env_bool("__TEST_ENV__", True) is True
    assert _env_bool("__TEST_ENV__", False) is False
    os.environ.pop("__TEST_ENV__", None)


def test_cost_tracking_env_disables(monkeypatch):
    """F-17-ENV1: HIVE_SWARM_COST_TRACKING=0 disables cost tracking."""
    monkeypatch.setenv("HIVE_SWARM_COST_TRACKING", "0")
    settings = resolve_llm_settings(None, role="coder")
    assert settings["cost_tracking_enabled"] is False


def test_cost_tracking_env_enables_explicitly(monkeypatch):
    monkeypatch.setenv("HIVE_SWARM_COST_TRACKING", "true")
    settings = resolve_llm_settings(None, role="coder")
    assert settings["cost_tracking_enabled"] is True


def test_cost_tracking_env_overrides_queen_setting(monkeypatch):
    """Env wins over queen-forwarded settings."""
    monkeypatch.setenv("HIVE_SWARM_COST_TRACKING", "0")
    ctx = {"shared_context": {"llm_settings": {"cost_tracking_enabled": True}}}
    settings = resolve_llm_settings(ctx, role="coder")
    assert settings["cost_tracking_enabled"] is False


def test_default_cost_tracking_unchanged():
    assert DEFAULT_SETTINGS["cost_tracking_enabled"] is True
