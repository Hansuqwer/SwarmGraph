"""F-04D: SwarmState round-trip tests."""
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState


def test_state_round_trip_lossless():
    config = SwarmConfig(topology="hierarchical")
    s1 = SwarmState(swarm_id="s1", objective="implement OAuth", config=config)
    d = s1.to_json_dict()
    s2 = SwarmState.from_json_dict(d)
    assert s1.swarm_id == s2.swarm_id
    assert s1.objective == s2.objective
    assert s1.objective_hash == s2.objective_hash
    assert s1.config.topology == s2.config.topology


def test_objective_hash_auto_computed():
    config = SwarmConfig()
    s = SwarmState(swarm_id="s1", objective="implement OAuth", config=config)
    assert s.objective_hash != ""
    assert len(s.objective_hash) == 16


def test_objective_hash_stable_across_roundtrip():
    config = SwarmConfig()
    s1 = SwarmState(swarm_id="s1", objective="task A", config=config)
    s2 = SwarmState.from_json_dict(s1.to_json_dict())
    assert s1.objective_hash == s2.objective_hash


def test_history_capped_at_500():
    config = SwarmConfig()
    s = SwarmState(swarm_id="s1", objective="x", config=config)
    for i in range(600):
        s.append_history("worker_result", {"i": i})
    assert len(s.history) == 500
    # head_plus_tail strategy: keeps first + last
    # First entry is the i=0 entry; last is i=599
    assert s.history[0]["i"] == 0
    assert s.history[-1]["i"] == 599


def test_errors_capped_at_100():
    config = SwarmConfig()
    s = SwarmState(swarm_id="s1", objective="x", config=config)
    for i in range(150):
        s.add_error(f"err {i}")
    assert len(s.errors) == 100
    # tail strategy: keeps last 100
    assert s.errors[0] == "err 50"
    assert s.errors[-1] == "err 149"


def test_add_error_updates_touch():
    """F-09C: add_error calls touch()."""
    config = SwarmConfig()
    s = SwarmState(swarm_id="s1", objective="x", config=config)
    before = s.updated_at
    s.add_error("oops")
    assert s.updated_at >= before


def test_assert_no_drift_raises_before_mutating_validators():
    """F-09A: ValueError raised even when other validators would otherwise complain."""
    config = SwarmConfig(anti_drift_enabled=True, anti_drift_similarity_threshold=0.9)
    s = SwarmState(swarm_id="s1", objective="implement OAuth refresh tokens", config=config)
    import pytest
    with pytest.raises(ValueError, match="Anti-drift"):
        s.assert_no_drift("totally unrelated output")


def test_reset_for_retry_clears_ephemeral_state():
    """F-18A: clean retry."""
    from swarm.models.agent import WorkerResult
    config = SwarmConfig()
    s = SwarmState(swarm_id="s1", objective="x", config=config)
    s.worker_results = [
        WorkerResult(agent_id="a1", agent_role="coder", task_id="t1",
                     success=True, output="ok", confidence=0.8)
    ]
    s.latest_output = "stale"
    s.reset_for_retry()
    assert s.worker_results == []
    assert s.latest_output == ""
    assert s.consensus_result is None
    assert s.status == "routing"


def test_schema_version_default():
    """F-09B: schema_version present."""
    config = SwarmConfig()
    s = SwarmState(swarm_id="s1", objective="x", config=config)
    assert s.schema_version == 1
