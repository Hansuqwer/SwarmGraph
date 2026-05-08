"""Tests for `ai-provider-gateway audit verify` subcommand."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_provider_swarm_gateway.cli import app
from swarm_shared.audit import AuditChain, AuditRecord


SECRET = "test-audit-hmac-secret-32bytes-of-entropy-here"
runner = CliRunner()


# ── audit verify subcommand surface ─────────────────────────────────────

def test_audit_verify_help_works():
    result = runner.invoke(app, ["audit", "verify", "--help"])
    assert result.exit_code == 0
    assert "audit log" in result.stdout.lower() or "verify" in result.stdout.lower()


def test_audit_verify_clean_log_exits_zero(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(3):
        chain.append(kind="worker_result", payload={"i": i})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 0
    assert "3" in result.stdout or "verified" in result.stdout.lower()


def test_audit_verify_json_output(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    chain.append(kind="consensus_result", payload={"x": 1})
    chain.append(kind="worker_result", payload={"x": 2})
    chain.append(kind="worker_result", payload={"x": 3})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(log_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["verified"] == 3
    assert payload["by_kind"]["consensus_result"] == 1
    assert payload["by_kind"]["worker_result"] == 2


# ── Failure modes ──────────────────────────────────────────────────────

def test_audit_verify_missing_secret_exits_1(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    chain.append(kind="worker_result", payload={"x": 1})

    monkeypatch.delenv("HIVE_SWARM_AUDIT_SECRET", raising=False)
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 1
    out = result.stdout + (result.stderr or "")
    assert "unset" in out.lower() or "secret" in out.lower()


def test_audit_verify_missing_file_exits_typer_error(tmp_path: Path, monkeypatch):
    """Typer's exists=True validation catches this before our code runs."""
    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(tmp_path / "nonexistent.jsonl")])
    # Typer rejects with exit code 2 (its standard validation failure)
    assert result.exit_code != 0


def test_audit_verify_malformed_log_exits_2(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "bad.jsonl"
    log_path.write_text("{not valid json\n")

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 2


def test_audit_verify_tampered_log_exits_3(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(3):
        chain.append(kind="worker_result", payload={"i": i})

    # Tamper with the second line
    lines = log_path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["payload"] = {"i": 999}   # original was {"i": 1}
    lines[1] = json.dumps(rec)
    log_path.write_text("\n".join(lines) + "\n")

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 3
    out = result.stdout + (result.stderr or "")
    assert "broken" in out.lower() or "mismatch" in out.lower() or "tampered" in out.lower()


def test_audit_verify_wrong_secret_exits_3(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    chain.append(kind="worker_result", payload={"x": 1})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", "completely-different-secret")
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 3


def test_audit_verify_deleted_record_exits_3(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(5):
        chain.append(kind="worker_result", payload={"i": i})

    # Delete record at index 2 (middle)
    lines = log_path.read_text().splitlines()
    del lines[2]
    log_path.write_text("\n".join(lines) + "\n")

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 3


def test_audit_verify_reordered_records_exits_3(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(4):
        chain.append(kind="worker_result", payload={"i": i})

    # Swap lines 1 and 2
    lines = log_path.read_text().splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    log_path.write_text("\n".join(lines) + "\n")

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 3


def test_audit_verify_inserted_record_exits_3(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    chain.append(kind="worker_result", payload={"x": 1})
    chain.append(kind="worker_result", payload={"x": 2})

    # Forge a third record signed with the same secret but with sequence=1
    # (collides with existing sequence 1 → sequence break)
    fake = chain.records[1].model_dump()   # cheap: clone existing
    fake["payload"] = {"injected": True}   # tamper
    lines = log_path.read_text().splitlines()
    lines.insert(1, json.dumps(fake))
    log_path.write_text("\n".join(lines) + "\n")

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 3


# ── Empty + edge cases ─────────────────────────────────────────────────

def test_audit_verify_empty_log_exits_zero(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    log_path.write_text("")
    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, ["audit", "verify", str(log_path)])
    assert result.exit_code == 0
    assert "empty" in result.stdout.lower() or "0" in result.stdout


# ── Pinned audit verification CLI flags ─────────────────────────────────

def test_audit_verify_expected_head_hash_pass(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(3):
        chain.append(kind="worker_result", payload={"i": i})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, [
        "audit", "verify", str(log_path),
        "--expected-head-hash", chain.head_hash,
    ])

    assert result.exit_code == 0


def test_audit_verify_expected_head_hash_fail(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(3):
        chain.append(kind="worker_result", payload={"i": i})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, [
        "audit", "verify", str(log_path),
        "--expected-head-hash", "a" * 64,
    ])

    assert result.exit_code == 3
    assert "head hash" in (result.stdout + (result.stderr or "")).lower()


def test_audit_verify_expected_count_pass(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(4):
        chain.append(kind="worker_result", payload={"i": i})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, [
        "audit", "verify", str(log_path),
        "--expected-count", "4",
    ])

    assert result.exit_code == 0


def test_audit_verify_expected_count_fail(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(3):
        chain.append(kind="worker_result", payload={"i": i})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, [
        "audit", "verify", str(log_path),
        "--expected-count", "10",
    ])

    assert result.exit_code == 3
    assert "count" in (result.stdout + (result.stderr or "")).lower()


def test_audit_verify_both_pins_pass(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(5):
        chain.append(kind="worker_result", payload={"i": i})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, [
        "audit", "verify", str(log_path),
        "--expected-head-hash", chain.head_hash,
        "--expected-count", "5",
    ])

    assert result.exit_code == 0


def test_audit_verify_both_pins_wrong_count_exits_3(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(3):
        chain.append(kind="worker_result", payload={"i": i})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, [
        "audit", "verify", str(log_path),
        "--expected-head-hash", chain.head_hash,
        "--expected-count", "99",
    ])

    assert result.exit_code == 3


def test_audit_verify_json_output_includes_pins(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(2):
        chain.append(kind="worker_result", payload={"i": i})

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, [
        "audit", "verify", str(log_path), "--json",
        "--expected-head-hash", chain.head_hash,
        "--expected-count", "2",
    ])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["expected_head_hash"] == chain.head_hash
    assert payload["expected_count"] == 2


def test_audit_verify_empty_log_with_expected_count_nonzero_exits_3(
    tmp_path: Path,
    monkeypatch,
):
    log_path = tmp_path / "audit.jsonl"
    log_path.write_text("")

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    result = runner.invoke(app, [
        "audit", "verify", str(log_path),
        "--expected-count", "5",
    ])

    assert result.exit_code == 3


def test_audit_verify_truncated_log_caught_by_head_hash_pin(
    tmp_path: Path,
    monkeypatch,
):
    log_path = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=log_path)
    for i in range(5):
        chain.append(kind="worker_result", payload={"i": i})
    full_head = chain.head_hash

    lines = log_path.read_text().splitlines()[:3]
    log_path.write_text("\n".join(lines) + "\n")

    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", SECRET)
    assert runner.invoke(app, ["audit", "verify", str(log_path)]).exit_code == 0
    result = runner.invoke(app, [
        "audit", "verify", str(log_path),
        "--expected-head-hash", full_head,
    ])

    assert result.exit_code == 3


def test_audit_verify_help_shows_pin_flags():
    result = runner.invoke(app, ["audit", "verify", "--help"])

    assert result.exit_code == 0
    assert "--expected-head-hash" in result.stdout
    assert "--expected-count" in result.stdout
