"""Tests for --tenant flag end-to-end through the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_provider_swarm_gateway.cli import app

runner = CliRunner()


# ── --tenant flag plumbing through quota commands ───────────────────────


def test_quota_increment_tenant_flag(tmp_path: Path, monkeypatch):
    """--tenant alice writes to alice's storage path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Reset the tracker module to pick up the new HOME
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    result = runner.invoke(
        app,
        [
            "quota",
            "increment",
            "--provider",
            "openai",
            "--requests",
            "5",
            "--tokens",
            "100",
            "--tenant",
            "alice",
        ],
    )
    assert result.exit_code == 0

    expected_path = tmp_path / ".ai_provider_gateway" / "tenants" / "alice" / "usage.json"
    assert expected_path.exists()
    data = json.loads(expected_path.read_text())
    assert data["openai:daily"]["used_requests"] == 5


def test_quota_show_two_tenants_isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    runner.invoke(
        app, ["quota", "increment", "--provider", "openai", "--requests", "10", "--tenant", "alice"]
    )
    runner.invoke(
        app, ["quota", "increment", "--provider", "openai", "--requests", "3", "--tenant", "bob"]
    )

    # Show alice
    result_alice = runner.invoke(app, ["quota", "show", "--tenant", "alice", "--json"])
    assert result_alice.exit_code == 0
    alice_payload = json.loads(result_alice.stdout)
    assert any(row["used_requests"] == 10 for row in alice_payload)

    # Show bob — must NOT see alice's number
    result_bob = runner.invoke(app, ["quota", "show", "--tenant", "bob", "--json"])
    assert result_bob.exit_code == 0
    bob_payload = json.loads(result_bob.stdout)
    assert any(row["used_requests"] == 3 for row in bob_payload)
    assert not any(row["used_requests"] == 10 for row in bob_payload)


def test_quota_reset_tenant_isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    runner.invoke(
        app, ["quota", "increment", "--provider", "openai", "--requests", "10", "--tenant", "alice"]
    )
    runner.invoke(
        app, ["quota", "increment", "--provider", "openai", "--requests", "10", "--tenant", "bob"]
    )

    # Reset alice only
    result = runner.invoke(
        app,
        ["quota", "reset", "--provider", "openai", "--yes", "--tenant", "alice"],
    )
    assert result.exit_code == 0

    # Bob's usage untouched
    bob_show = runner.invoke(app, ["quota", "show", "--tenant", "bob", "--json"])
    bob_payload = json.loads(bob_show.stdout)
    assert any(row["used_requests"] == 10 for row in bob_payload)


# ── tenants subcommand ──────────────────────────────────────────────────


def test_tenants_list_empty_initially(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    result = runner.invoke(app, ["tenants", "list"])
    assert result.exit_code == 0
    out = result.stdout.lower()
    assert "no tenants" in out or "[" in out


def test_tenants_list_after_create(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai", "--requests", "1", "--tenant", "team_alpha"],
    )
    runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai", "--requests", "1", "--tenant", "team_beta"],
    )

    result = runner.invoke(app, ["tenants", "list", "--json"])
    assert result.exit_code == 0
    listed = json.loads(result.stdout)
    assert "team_alpha" in listed
    assert "team_beta" in listed


def test_tenants_storage_path():
    result = runner.invoke(app, ["tenants", "storage-path", "alice"])
    assert result.exit_code == 0
    assert "alice" in result.stdout
    assert "usage.json" in result.stdout


def test_tenants_storage_path_rejects_invalid():
    """Path traversal must be blocked at validation time."""
    result = runner.invoke(app, ["tenants", "storage-path", "../escape"])
    assert result.exit_code != 0


# ── F-30-COSM1 regression: empty-quota messages render ──────────────────


def test_empty_quota_message_renders_with_brackets(tmp_path: Path, monkeypatch):
    """The Rich-markup-swallowing bug: '[no usage recorded yet]' must
    appear in stdout (verbatim brackets), not be eaten as a style tag."""
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    result = runner.invoke(app, ["quota", "show"])
    assert result.exit_code == 0
    # Either literal brackets OR escaped form should appear; what must NOT
    # happen is empty output (Rich would eat the brackets entirely).
    assert "no usage recorded yet" in result.stdout.lower()


def test_empty_quota_with_since_message_renders(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    runner.invoke(
        app, ["quota", "increment", "--provider", "openai", "--requests", "1", "--tenant", "alice"]
    )
    # Set the reset_at to 30 days ago so --since 1h filters it out
    from datetime import datetime, timedelta, timezone

    fp = tracker_mod.QuotaTracker.tenant_storage_path("alice")
    data = json.loads(fp.read_text())
    old = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()
    for k in data:
        data[k]["reset_at"] = old
    fp.write_text(json.dumps(data))

    result = runner.invoke(app, ["quota", "show", "--tenant", "alice", "--since", "1h"])
    assert result.exit_code == 0
    assert "no usage in last 1h" in result.stdout.lower()
