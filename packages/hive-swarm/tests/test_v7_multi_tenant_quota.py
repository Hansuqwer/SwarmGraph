"""Tests for multi-tenant QuotaTracker isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_provider_swarm_gateway.quota.tracker import (
    QuotaTracker,
    _validate_tenant_id,
)


# ── Tenant id validation ────────────────────────────────────────────────


def test_valid_tenant_ids():
    for tid in ("alice", "team_blue", "tenant-001", "ABC123", "a"):
        assert _validate_tenant_id(tid) == tid


def test_invalid_tenant_ids_rejected():
    for tid in ("../escape", "with space", "name@host", "name/path", "", "x" * 65):
        with pytest.raises(ValueError):
            _validate_tenant_id(tid)


def test_validate_no_traversal_via_dotdot():
    """Path traversal protection."""
    with pytest.raises(ValueError):
        _validate_tenant_id("..")
    with pytest.raises(ValueError):
        _validate_tenant_id("../../etc/passwd")


# ── tenant_storage_path ──────────────────────────────────────────────────


def test_tenant_storage_path_contains_tenant_id():
    path = QuotaTracker.tenant_storage_path("alice")
    assert "alice" in str(path)
    assert "tenants" in str(path)
    assert path.name == "usage.json"


def test_tenant_storage_path_rejects_invalid():
    with pytest.raises(ValueError):
        QuotaTracker.tenant_storage_path("../bad")


# ── Construction modes ──────────────────────────────────────────────────


def test_constructor_storage_path_takes_precedence(tmp_path: Path):
    fp = tmp_path / "explicit.json"
    t = QuotaTracker(storage_path=fp)
    assert t.storage_path == fp
    assert t.tenant_id is None


def test_constructor_tenant_id_sets_canonical_path():
    t = QuotaTracker(tenant_id="alice")
    assert t.tenant_id == "alice"
    assert "alice" in str(t.storage_path)


def test_constructor_both_args_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="either"):
        QuotaTracker(storage_path=tmp_path / "x.json", tenant_id="alice")


def test_for_tenant_factory_works():
    t = QuotaTracker.for_tenant("bob")
    assert t.tenant_id == "bob"


def test_env_var_picked_up_when_no_args(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_TENANT", "from-env")
    t = QuotaTracker()
    assert t.tenant_id == "from-env"


def test_env_var_invalid_id_raises(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_TENANT", "../bad")
    with pytest.raises(ValueError):
        QuotaTracker()


def test_env_var_overridden_by_explicit_storage(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_TENANT", "alice")
    fp = tmp_path / "u.json"
    t = QuotaTracker(storage_path=fp)
    # Explicit storage wins; tenant_id stays None
    assert t.storage_path == fp
    assert t.tenant_id is None


# ── Isolation: two tenants don't see each other's usage ─────────────────


def test_two_tenants_isolated(tmp_path: Path, monkeypatch):
    """Critical: tenant alice's quota MUST NOT leak into tenant bob's view."""
    # Use temp dir as the home base by monkey-patching expanduser
    monkeypatch.setenv("HOME", str(tmp_path))
    # Recompute the default base after env change
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    alice = tracker_mod.QuotaTracker.for_tenant("alice")
    bob = tracker_mod.QuotaTracker.for_tenant("bob")

    alice.increment("openai", requests=10, tokens=500)
    bob.increment("openai", requests=3, tokens=100)

    assert alice.get_usage("openai").used_requests == 10
    assert alice.get_usage("openai").used_tokens == 500
    assert bob.get_usage("openai").used_requests == 3
    assert bob.get_usage("openai").used_tokens == 100

    # Storage paths are distinct
    assert alice.storage_path != bob.storage_path
    assert "alice" in str(alice.storage_path)
    assert "bob" in str(bob.storage_path)


def test_list_tenants_returns_only_real_dirs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    # Empty initially
    assert tracker_mod.QuotaTracker.list_tenants() == []

    # Create a couple of tenants
    tracker_mod.QuotaTracker.for_tenant("alice").increment("openai", requests=1)
    tracker_mod.QuotaTracker.for_tenant("bob").increment("anthropic", requests=1)
    listed = tracker_mod.QuotaTracker.list_tenants()
    assert "alice" in listed
    assert "bob" in listed


def test_single_tenant_default_unchanged(monkeypatch, tmp_path: Path):
    """Back-compat: no tenant id → default ~/.ai_provider_gateway/usage.json path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AI_PROVIDER_GATEWAY_TENANT", raising=False)
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    t = tracker_mod.QuotaTracker()
    assert t.tenant_id is None
    # Path is the legacy single-tenant location, NOT under tenants/
    assert "tenants" not in str(t.storage_path)
    assert t.storage_path.name == "usage.json"


def test_reset_only_affects_one_tenant(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    from ai_provider_swarm_gateway.quota import tracker as tracker_mod

    importlib.reload(tracker_mod)

    alice = tracker_mod.QuotaTracker.for_tenant("alice")
    bob = tracker_mod.QuotaTracker.for_tenant("bob")

    alice.increment("openai", requests=10)
    bob.increment("openai", requests=10)

    alice.reset_usage("openai")

    assert alice.get_usage("openai").used_requests == 0
    assert bob.get_usage("openai").used_requests == 10  # untouched
