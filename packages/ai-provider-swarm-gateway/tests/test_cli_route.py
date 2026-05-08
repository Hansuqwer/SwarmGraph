"""Tests for the lifted `route` command.

These tests use the upstream `mock` adapter (which is always-configured per
the analysis trace) so they don't need real API keys. If the gateway was not
fully vendored on this machine, route-specific tests xfail with a clear
reason instead of crashing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_provider_swarm_gateway.cli import app

runner = CliRunner()


# ── Detect whether the upstream gateway is fully vendored ────────────────

def _gateway_fully_vendored() -> bool:
    try:
        from ai_provider_swarm_gateway.models.state import GatewayState  # noqa: F401
        from ai_provider_swarm_gateway.graph.builder import build_gateway_graph  # noqa: F401
        return True
    except Exception:
        return False


GATEWAY_OK = _gateway_fully_vendored()
SKIP_REASON = "upstream gateway not fully vendored (RR1 incomplete)"


# ── inspect-state always works (degrades gracefully) ─────────────────────

def test_inspect_state_runs_or_explains():
    result = runner.invoke(app, ["inspect-state"])
    if GATEWAY_OK:
        assert result.exit_code == 0
        assert "user_prompt" in result.stdout or "audit_log" in result.stdout
    else:
        # Without the upstream pieces, exit 2 with a clear message
        assert result.exit_code == 2
        assert "GatewayState" in (result.stdout + (result.stderr or ""))


def test_inspect_state_json():
    if not GATEWAY_OK:
        pytest.skip(SKIP_REASON)
    result = runner.invoke(app, ["inspect-state", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert any(row["name"] == "user_prompt" for row in data)


# ── route — happy paths via mock adapter ─────────────────────────────────

@pytest.mark.skipif(not GATEWAY_OK, reason=SKIP_REASON)
def test_route_with_mock_provider_dry_run():
    """Hint the mock adapter; --dry-run skips the actual provider call."""
    result = runner.invoke(
        app,
        ["route", "--prompt", "say hi", "--preferred", "mock",
         "--dry-run", "--json"],
    )
    # dry-run with mock should at least classify and select; exit codes:
    # 0 = success, 4 = no provider selected (fine for dry-run if so)
    assert result.exit_code in (0, 4)
    payload = json.loads(result.stdout.strip().split("\n")[-1] if "{" in result.stdout else result.stdout)
    assert payload["thread_id"].startswith("cli-")
    assert payload["prompt"] == "say hi"


@pytest.mark.skipif(not GATEWAY_OK, reason=SKIP_REASON)
def test_route_capability_inference():
    """When --capability omitted, classify_request_node infers chat by default."""
    result = runner.invoke(
        app,
        ["route", "--prompt", "hello world", "--preferred", "mock",
         "--dry-run", "--json"],
    )
    assert result.exit_code in (0, 4)
    # Either way, the JSON should parse and include candidate_providers list
    out = result.stdout.strip()
    last_json_line = out[out.find("{"):]
    payload = json.loads(last_json_line)
    assert "candidate_providers" in payload


@pytest.mark.skipif(not GATEWAY_OK, reason=SKIP_REASON)
def test_route_thread_id_propagates():
    custom_tid = "test-tid-explicit-12345"
    result = runner.invoke(
        app,
        ["route", "--prompt", "x", "--preferred", "mock",
         "--thread-id", custom_tid, "--dry-run", "--json"],
    )
    assert result.exit_code in (0, 4)
    out = result.stdout.strip()
    last_json_line = out[out.find("{"):]
    payload = json.loads(last_json_line)
    assert payload["thread_id"] == custom_tid


@pytest.mark.skipif(not GATEWAY_OK, reason=SKIP_REASON)
def test_route_show_audit_includes_audit_log():
    result = runner.invoke(
        app,
        ["route", "--prompt", "x", "--preferred", "mock",
         "--dry-run", "--json", "--show-audit"],
    )
    assert result.exit_code in (0, 4)
    # show-audit emits a second JSON object with audit_log key
    assert "audit_log" in result.stdout


# ── route — failure mode: missing required upstream module ───────────────

def test_route_explains_when_gateway_missing(monkeypatch):
    """If the import resolution fails, route should exit 2 with an actionable message."""
    if GATEWAY_OK:
        # Simulate the missing-import failure by monkeypatching the helper
        from ai_provider_swarm_gateway import cli as cli_mod

        def _broken_import():
            raise ImportError("simulated: models.state missing")

        monkeypatch.setattr(cli_mod, "_import_gateway_pieces", _broken_import)
        result = runner.invoke(app, ["route", "--prompt", "x"])
        assert result.exit_code == 2
        assert "Vendor them into" in (result.stdout + (result.stderr or ""))
    else:
        # Naturally missing — same expected behaviour
        result = runner.invoke(app, ["route", "--prompt", "x"])
        assert result.exit_code == 2


# ── providers list — registry shape (regression for the YAML-shape fix) ─

def test_providers_list_handles_upstream_yaml_shape():
    """Regression: upstream uses {providers: [...]} not bare list."""
    result = runner.invoke(app, ["providers", "list", "--json"])
    if result.exit_code == 0:
        payload = json.loads(result.stdout)
        assert isinstance(payload, list)
        # Every entry should have at least provider_id; name normalisation handled by CLI
        assert all("provider_id" in p for p in payload)
    else:
        # No registry vendored → exit 2 (acceptable)
        assert result.exit_code == 2


def test_providers_list_capability_filter():
    if runner.invoke(app, ["providers", "list", "--json"]).exit_code != 0:
        pytest.skip("no registry vendored")
    result = runner.invoke(app, ["providers", "list", "--capability", "chat", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert all("chat" in (p.get("capabilities") or []) for p in payload)


def test_providers_list_free_only_filter():
    base = runner.invoke(app, ["providers", "list", "--json"])
    if base.exit_code != 0:
        pytest.skip("no registry vendored")
    full = json.loads(base.stdout)
    result = runner.invoke(app, ["providers", "list", "--free-only", "--json"])
    assert result.exit_code == 0
    free_only = json.loads(result.stdout)
    # Subset relation
    assert len(free_only) <= len(full)
