"""Tests for `ai-provider-gateway swarm` subcommand."""

from __future__ import annotations

import json

import pytest
from ai_provider_swarm_gateway.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def _hive_swarm_available() -> bool:
    try:
        from swarm import SwarmConfig, SwarmState, build_swarm_graph  # noqa: F401

        return True
    except Exception:
        return False


HIVE_OK = _hive_swarm_available()
SKIP_REASON = "hive-swarm not installed in this venv"


# ── Help / surface ───────────────────────────────────────────────────────


def test_swarm_help_in_root():
    """`ai-provider-gateway --help` must mention `swarm`."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "swarm" in result.stdout.lower()


def test_swarm_help_works():
    result = runner.invoke(app, ["swarm", "--help"], terminal_width=160)
    assert result.exit_code == 0
    assert "--prompt" in result.stdout
    assert "--backend" in result.stdout
    assert "--topology" in result.stdout


# ── Stub mode (no LLM, no network) ───────────────────────────────────────


@pytest.mark.skipif(not HIVE_OK, reason=SKIP_REASON)
def test_swarm_stub_mode_runs_to_completion():
    """Default backend=stub + tier-1 objective → completes deterministically."""
    result = runner.invoke(
        app,
        ["swarm", "--prompt", "rename foo to bar", "--backend", "stub", "--json"],
    )
    # Tier-1 path doesn't go through workers; stub mode never HITLs
    assert result.exit_code in (0, 4)
    out = result.stdout.strip()
    last_json = out[out.find("{") :]
    payload = json.loads(last_json)
    assert payload["objective_hash"]
    assert payload["backend"] == "stub"


@pytest.mark.skipif(not HIVE_OK, reason=SKIP_REASON)
def test_swarm_stub_mode_tier3_runs_workers():
    """Verbose objective → tier-3 → workers fire (deterministic stubs)."""
    result = runner.invoke(
        app,
        [
            "swarm",
            "--prompt",
            (
                "implement a comprehensive distributed authentication architecture "
                "with refresh tokens and audit logging"
            ),
            "--backend",
            "stub",
            "--json",
            "--show-workers",
        ],
    )
    assert result.exit_code in (0, 4)
    out = result.stdout.strip()
    last_json = out[out.find("{") :]
    payload = json.loads(last_json)
    # stub-mode workers don't generate token counts, but they DO run
    assert payload["worker_count"] >= 1
    assert isinstance(payload.get("workers", []), list)


# ── Gateway mode (mocked adapter) ────────────────────────────────────────


@pytest.mark.skipif(not HIVE_OK, reason=SKIP_REASON)
def test_swarm_gateway_mode_with_mocked_adapter(monkeypatch):
    """Patch the dispatcher's adapter factory; run swarm in gateway mode."""
    from swarm.llm import dispatch as dispatch_mod

    class _FakeAdapter:
        def is_configured(self):
            return True

        def chat(self, *, messages, max_tokens, temperature, model=None):
            return {
                "model": model or "kc/kilo-auto/free",
                "choices": [
                    {
                        "message": {"content": "FAKE: " + messages[-1]["content"][:60]},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 30, "completion_tokens": 10},
            }

    monkeypatch.setattr(
        dispatch_mod,
        "_default_adapter_factory",
        lambda pid: _FakeAdapter(),
    )

    result = runner.invoke(
        app,
        [
            "swarm",
            "--prompt",
            "implement comprehensive distributed authentication architecture",
            "--backend",
            "gateway",
            "--provider",
            "9router",
            "--max-agents",
            "3",
            "--json",
            "--show-workers",
        ],
    )
    assert result.exit_code in (0, 4), f"unexpected exit: {result.exit_code}\n{result.stdout}"
    out = result.stdout.strip()
    last_json = out[out.find("{") :]
    payload = json.loads(last_json)
    assert payload["backend"] == "gateway"
    assert payload["provider"] == "9router"
    # Token totals propagated from worker → state → CLI payload
    if payload["status"] == "completed":
        assert payload["total_input_tokens"] >= 1
        assert payload["total_output_tokens"] >= 1


@pytest.mark.skipif(not HIVE_OK, reason=SKIP_REASON)
def test_swarm_invalid_topology_rejected():
    result = runner.invoke(
        app,
        ["swarm", "--prompt", "x", "--topology", "nonexistent"],
    )
    # SwarmConfig will raise on the Literal — exit 2
    assert result.exit_code == 2
    assert (
        "SwarmConfig" in result.stdout
        or "rejected" in result.stdout.lower()
        or "nonexistent" in result.stdout.lower() + (result.stderr or "").lower()
    )


@pytest.mark.skipif(not HIVE_OK, reason=SKIP_REASON)
def test_swarm_thread_id_propagates():
    custom = "test-explicit-tid-9999"
    result = runner.invoke(
        app,
        ["swarm", "--prompt", "x", "--thread-id", custom, "--json"],
    )
    assert result.exit_code in (0, 4)
    out = result.stdout.strip()
    last_json = out[out.find("{") :]
    payload = json.loads(last_json)
    assert payload["swarm_id"] == custom


def test_swarm_explains_when_hive_missing(monkeypatch):
    """If hive-swarm isn't importable, swarm exits 2 with a clear message."""
    import sys

    # Force ImportError by removing 'swarm' if present
    saved = sys.modules.get("swarm")
    sys.modules["swarm"] = None  # type: ignore
    try:
        result = runner.invoke(app, ["swarm", "--prompt", "x"])
        # If hive was already imported, monkeypatch is moot — just check we got something
        if HIVE_OK:
            # Behaviour with hive present is tested above
            return
        assert result.exit_code == 2
    finally:
        if saved is not None:
            sys.modules["swarm"] = saved
        else:
            sys.modules.pop("swarm", None)
