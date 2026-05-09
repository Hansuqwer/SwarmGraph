"""Tests for audit signing in consensus / approval / worker nodes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from swarm_shared.audit import (
    GENESIS_PREV_HASH,
    AuditChainBroken,
    AuditRecord,
    load_jsonl_chain,
    verify_chain,
)

SECRET_VALUE = "test-hmac-secret-32bytes-of-entropy-here-please"


@pytest.fixture
def audit_env(monkeypatch):
    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET_VALUE)


# ── _audit_helper unit tests ────────────────────────────────────────────


def test_sign_and_record_no_op_when_disabled(audit_env):
    """audit_signing_enabled=False ⇒ sign_and_record returns None."""
    from swarm._audit_helper import sign_and_record
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState

    state = SwarmState(
        swarm_id="s1",
        objective="x",
        config=SwarmConfig(audit_signing_enabled=False),
    )
    assert sign_and_record(state, "consensus_result", {"x": 1}) is None
    assert state.audit_records == []


def test_sign_and_record_writes_when_enabled(audit_env):
    from swarm._audit_helper import sign_and_record
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState

    state = SwarmState(
        swarm_id="s1",
        objective="x",
        config=SwarmConfig(audit_signing_enabled=True),
    )
    rec_dict = sign_and_record(state, "consensus_result", {"vote_count": 5})
    assert rec_dict is not None
    assert rec_dict["kind"] == "consensus_result"
    assert rec_dict["sequence"] == 0
    assert rec_dict["prev_hash"] == GENESIS_PREV_HASH
    assert state.audit_chain_head == rec_dict["record_hash"]
    assert state.audit_sequence == 1


def test_sign_and_record_chain_links(audit_env):
    """Two records back-to-back: second's prev_hash == first's record_hash."""
    from swarm._audit_helper import sign_and_record
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState

    state = SwarmState(
        swarm_id="s1",
        objective="x",
        config=SwarmConfig(audit_signing_enabled=True),
    )
    r1 = sign_and_record(state, "consensus_result", {"i": 1})
    r2 = sign_and_record(state, "approval_decision", {"i": 2})
    assert r1["sequence"] == 0
    assert r2["sequence"] == 1
    assert r2["prev_hash"] == r1["record_hash"]


def test_sign_and_record_skipped_for_unconfigured_kind(audit_env):
    """A kind not in audit_kinds is silently skipped."""
    from swarm._audit_helper import sign_and_record
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState

    state = SwarmState(
        swarm_id="s1",
        objective="x",
        config=SwarmConfig(
            audit_signing_enabled=True,
            audit_kinds=("consensus_result",),  # only consensus
        ),
    )
    r1 = sign_and_record(state, "consensus_result", {"x": 1})
    r2 = sign_and_record(state, "worker_result", {"x": 2})  # excluded
    assert r1 is not None
    assert r2 is None
    assert len(state.audit_records) == 1


def test_sign_and_record_missing_secret_writes_error(monkeypatch):
    """audit_signing_enabled=True but secret env unset → error in state.errors,
    no audit record written, swarm doesn't crash."""
    from swarm._audit_helper import sign_and_record
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState

    # Ensure no secret
    monkeypatch.delenv("HIVE_SWARM_AUDIT_SECRET", raising=False)
    state = SwarmState(
        swarm_id="s1",
        objective="x",
        config=SwarmConfig(
            audit_signing_enabled=True,
            audit_secret_env="HIVE_SWARM_AUDIT_SECRET",
        ),
    )
    rec = sign_and_record(state, "consensus_result", {"x": 1})
    assert rec is None
    assert len(state.errors) == 1
    assert "HIVE_SWARM_AUDIT_SECRET" in state.errors[0]
    assert state.audit_records == []


def test_sign_and_record_missing_secret_can_fail_closed(monkeypatch):
    from swarm._audit_helper import AuditMisconfigured, sign_and_record
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState

    monkeypatch.delenv("HIVE_SWARM_AUDIT_SECRET", raising=False)
    state = SwarmState(
        swarm_id="s1",
        objective="x",
        config=SwarmConfig(
            audit_signing_enabled=True,
            audit_fail_closed=True,
            audit_secret_env="HIVE_SWARM_AUDIT_SECRET",
        ),
    )

    with pytest.raises(AuditMisconfigured):
        sign_and_record(state, "consensus_result", {"x": 1})
    assert state.audit_records == []
    assert state.errors


# ── Persistent JSONL flush ──────────────────────────────────────────────


def test_audit_jsonl_path_appends_records(audit_env, tmp_path: Path):
    from swarm._audit_helper import sign_and_record
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState

    audit_path = tmp_path / "audit.jsonl"
    state = SwarmState(
        swarm_id="s1",
        objective="x",
        config=SwarmConfig(
            audit_signing_enabled=True,
            audit_log_path=str(audit_path),
        ),
    )
    sign_and_record(state, "consensus_result", {"i": 1})
    sign_and_record(state, "consensus_result", {"i": 2})

    assert audit_path.exists()
    loaded = load_jsonl_chain(audit_path)
    assert len(loaded) == 2
    secret = SECRET_VALUE.encode("utf-8")
    assert verify_chain(loaded, secret=secret) == 2


def test_audit_log_path_substitutes_placeholders(audit_env, tmp_path: Path):
    from swarm.models.config import SwarmConfig

    template = str(tmp_path / "audit-{tenant}-{swarm_id}.jsonl")
    config = SwarmConfig(audit_log_path=template, audit_signing_enabled=True)

    resolved = config.resolve_audit_log_path(swarm_id="s1", tenant_id="alice")
    assert "alice" in resolved
    assert "s1" in resolved
    assert "{" not in resolved


# ── Integration: consensus + approval + worker all sign ─────────────────


def test_consensus_node_signs_result(audit_env):
    from swarm.models.agent import AgentVote
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState
    from swarm.nodes.consensus import consensus_node

    config = SwarmConfig(audit_signing_enabled=True)
    state = SwarmState(swarm_id="s1", objective="x", config=config)
    state.pending_votes = [
        AgentVote(agent_id=f"a{i}", agent_role="coder", proposed_action="do thing", confidence=0.9)
        for i in range(3)
    ]
    out = consensus_node(state.to_json_dict())
    final = SwarmState.from_json_dict(out)
    # At least one consensus_result audit record
    consensus_records = [r for r in final.audit_records if r["kind"] == "consensus_result"]
    assert len(consensus_records) == 1


def test_collect_results_node_signs_each_worker_result(audit_env):
    from swarm.models.agent import WorkerResult
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState
    from swarm.models.task import SwarmTask
    from swarm.nodes.worker import collect_results_node

    config = SwarmConfig(audit_signing_enabled=True)
    state = SwarmState(swarm_id="s1", objective="x", config=config)
    state.tasks.append(
        SwarmTask(
            task_id="t1",
            description="x",
            status="assigned",
            assigned_to="a1",
        )
    )
    state.worker_results = [
        WorkerResult(
            agent_id="a1",
            agent_role="coder",
            task_id="t1",
            success=True,
            output="ok",
            confidence=0.9,
        ),
        WorkerResult(
            agent_id="a2",
            agent_role="tester",
            task_id="t1",
            success=False,
            error_message="failed",
            confidence=0.0,
        ),
    ]
    out = collect_results_node(state.to_json_dict())
    final = SwarmState.from_json_dict(out)

    worker_records = [r for r in final.audit_records if r["kind"] == "worker_result"]
    assert len(worker_records) == 2


def test_full_chain_verifies_after_consensus_and_workers(audit_env):
    """End-to-end: consensus + worker_result chain must verify cleanly."""
    from swarm.models.agent import AgentVote, WorkerResult
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState
    from swarm.models.task import SwarmTask
    from swarm.nodes.consensus import consensus_node
    from swarm.nodes.worker import collect_results_node

    config = SwarmConfig(audit_signing_enabled=True)
    state = SwarmState(swarm_id="s1", objective="x", config=config)

    # Add a task (required for collect_results to succeed)
    state.tasks.append(
        SwarmTask(
            task_id="t1",
            description="x",
            status="assigned",
            assigned_to="a1",
        )
    )
    state.worker_results = [
        WorkerResult(
            agent_id="a1",
            agent_role="coder",
            task_id="t1",
            success=True,
            output="ok",
            confidence=0.9,
        ),
    ]
    state.pending_votes = [
        AgentVote(agent_id="a1", agent_role="coder", proposed_action="do thing", confidence=0.9),
    ]

    # Run collect_results then consensus
    state_dict = collect_results_node(state.to_json_dict())
    final = SwarmState.from_json_dict(state_dict)
    state_dict = consensus_node(final.to_json_dict())
    final = SwarmState.from_json_dict(state_dict)

    # Reconstruct AuditRecord objects from the dicts in state.audit_records
    records = [AuditRecord.model_validate(d) for d in final.audit_records]
    secret = SECRET_VALUE.encode("utf-8")
    count = verify_chain(records, secret=secret)
    assert count == len(records)
    assert count >= 2  # at least 1 worker_result + 1 consensus_result


# ── SwarmConfig validation ──────────────────────────────────────────────


def test_invalid_audit_kind_rejected():
    from pydantic import ValidationError
    from swarm.models.config import SwarmConfig

    with pytest.raises(ValidationError):
        SwarmConfig(audit_kinds=("totally_made_up_kind",))


def test_invalid_secret_env_name_rejected():
    from pydantic import ValidationError
    from swarm.models.config import SwarmConfig

    with pytest.raises(ValidationError):
        SwarmConfig(audit_secret_env="lowercase-bad")


def test_streaming_pattern_validated_at_config_time():
    from pydantic import ValidationError
    from swarm.models.config import SwarmConfig

    with pytest.raises(ValidationError):
        SwarmConfig(streaming_guard_patterns=["[invalid regex"])


def test_streaming_max_chars_bound():
    from pydantic import ValidationError
    from swarm.models.config import SwarmConfig

    with pytest.raises(ValidationError):
        SwarmConfig(streaming_max_output_chars=10)  # below ge=128
