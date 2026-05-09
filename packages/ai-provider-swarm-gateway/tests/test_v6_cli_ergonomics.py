"""Tests for v6 CLI ergonomics: --since filter + canonized fixes + --stream + cost rollup."""

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from ai_provider_swarm_gateway.cli import _parse_duration_to_seconds, app
from typer.testing import CliRunner

runner = CliRunner()


# ── _parse_duration_to_seconds ───────────────────────────────────────────


def test_parse_duration_seconds():
    assert _parse_duration_to_seconds("30s") == 30
    assert _parse_duration_to_seconds("5m") == 300
    assert _parse_duration_to_seconds("1h") == 3600
    assert _parse_duration_to_seconds("7d") == 604800


def test_parse_duration_with_whitespace():
    assert _parse_duration_to_seconds("  30 m") == 1800  # space between
    # The regex tolerates the space: "30 m" → 30 m
    # If your local impl is stricter, adjust this test.


def test_parse_duration_invalid_format_raises():
    with pytest.raises(ValueError):
        _parse_duration_to_seconds("abc")
    with pytest.raises(ValueError):
        _parse_duration_to_seconds("10")  # missing unit
    with pytest.raises(ValueError):
        _parse_duration_to_seconds("10w")  # unsupported unit


# ── Canonized CLI fix #1: empty quota message ────────────────────────────


def test_quota_show_empty_uses_canonical_message(tmp_path: Path):
    fp = tmp_path / "usage.json"
    result = runner.invoke(app, ["quota", "show", "--storage", str(fp)])
    assert result.exit_code == 0
    # Both phrases acceptable; the canonized one is "[no usage recorded yet]"
    assert "no usage recorded yet" in result.stdout.lower()


# ── --since filter ──────────────────────────────────────────────────────


def test_quota_show_since_invalid_format_exits_2(tmp_path: Path):
    fp = tmp_path / "usage.json"
    runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai", "--requests", "1", "--storage", str(fp)],
    )
    result = runner.invoke(
        app,
        ["quota", "show", "--storage", str(fp), "--since", "garbage"],
    )
    assert result.exit_code == 2


def test_quota_show_since_filter_includes_no_reset_at(tmp_path: Path):
    """Entries without reset_at are included (conservative — unbounded windows)."""
    fp = tmp_path / "usage.json"
    runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai", "--requests", "1", "--storage", str(fp)],
    )
    result = runner.invoke(
        app,
        ["quota", "show", "--storage", str(fp), "--since", "1h", "--json"],
    )
    assert result.exit_code == 0
    # The increment didn't set reset_at, so it survives the filter
    payload = json.loads(result.stdout)
    assert any(row["provider"] == "openai" for row in payload)


def test_quota_show_since_filter_excludes_old(tmp_path: Path):
    """Entries with reset_at older than --since are filtered out."""
    fp = tmp_path / "usage.json"
    # Increment + set reset_at in the distant past
    runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai", "--requests", "1", "--storage", str(fp)],
    )
    # Manually edit usage.json to put reset_at far in the past
    data = json.loads(fp.read_text())
    old_time = (datetime.now(tz=UTC) - timedelta(days=30)).isoformat()
    for k in data:
        data[k]["reset_at"] = old_time
    fp.write_text(json.dumps(data))

    result = runner.invoke(
        app,
        ["quota", "show", "--storage", str(fp), "--since", "1h"],
    )
    # Should report empty for the filtered window
    assert result.exit_code == 0
    assert "no usage in last 1h" in result.stdout.lower() or "no usage" in result.stdout.lower()


# ── Canonized CLI fix #2: missing-gateway error ──────────────────────────


def test_route_missing_gateway_includes_vendor_them_into(monkeypatch):
    """If upstream import fails, the error message must include the
    'Vendor them into...' actionable line."""
    from ai_provider_swarm_gateway import cli as cli_mod

    def boom():
        raise ImportError("simulated import failure")

    monkeypatch.setattr(cli_mod, "_import_gateway_pieces", boom)
    result = runner.invoke(app, ["route", "--prompt", "x"])
    assert result.exit_code == 2
    out = result.stdout + (result.stderr or "")
    assert "Vendor them into" in out


# ── swarm --stream + cost rollup ─────────────────────────────────────────


def _hive_available():
    try:
        from swarm import SwarmConfig, build_swarm_graph  # noqa

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _hive_available(), reason="hive-swarm not installed")
def test_swarm_anti_drift_off_flag():
    """--anti-drift off should propagate into SwarmConfig."""
    result = runner.invoke(
        app,
        ["swarm", "--prompt", "test", "--anti-drift", "off", "--json"],
    )
    assert result.exit_code in (0, 4)
    out = result.stdout.strip()
    last_json = out[out.find("{") :]
    payload = json.loads(last_json)
    assert payload["anti_drift_mode"] == "off"


@pytest.mark.skipif(not _hive_available(), reason="hive-swarm not installed")
def test_swarm_invalid_anti_drift_rejected():
    result = runner.invoke(
        app,
        ["swarm", "--prompt", "test", "--anti-drift", "magic"],
    )
    # SwarmConfig rejects invalid mode
    assert result.exit_code == 2


@pytest.mark.skipif(not _hive_available(), reason="hive-swarm not installed")
def test_swarm_cost_rollup_in_json(monkeypatch):
    """Tier-3 swarm in gateway mode should emit total_cost_usd."""
    from swarm.llm import dispatch as dispatch_mod

    class _FakeAdapter:
        def is_configured(self):
            return True

        def chat(self, *, messages, max_tokens, temperature, model=None):
            # Return a priced model so cost is known
            return {
                "model": "claude-opus-4-7",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
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
            "--model",
            "claude-opus-4-7",
            "--anti-drift",
            "off",  # avoid retry storm in tests
            "--max-agents",
            "3",
            "--json",
        ],
    )
    assert result.exit_code in (0, 4)
    out = result.stdout.strip()
    last_json = out[out.find("{") :]
    payload = json.loads(last_json)
    # If the swarm completed and went through workers, cost should be populated
    if payload["worker_count"] >= 1:
        assert payload["total_cost_usd"] is not None


@pytest.mark.skipif(not _hive_available(), reason="hive-swarm not installed")
def test_swarm_no_cost_flag_disables_tracking(monkeypatch):
    from swarm.llm import dispatch as dispatch_mod

    class _FakeAdapter:
        def is_configured(self):
            return True

        def chat(self, *, messages, max_tokens, temperature, model=None):
            return {
                "model": "claude-opus-4-7",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
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
            "--model",
            "claude-opus-4-7",
            "--anti-drift",
            "off",
            "--max-agents",
            "3",
            "--no-cost",
            "--json",
        ],
    )
    assert result.exit_code in (0, 4)
    out = result.stdout.strip()
    last_json = out[out.find("{") :]
    payload = json.loads(last_json)
    # With cost tracking disabled, no individual worker has cost_usd set
    # → total_cost_usd is None
    if payload["worker_count"] >= 1:
        assert payload["total_cost_usd"] is None


@pytest.mark.skipif(not _hive_available(), reason="hive-swarm not installed")
def test_swarm_stream_flag_propagates(monkeypatch):
    """--stream sets llm_stream_enabled which propagates through queen → worker."""
    from swarm.llm import dispatch as dispatch_mod

    class _FakeStreamingAdapter:
        def is_configured(self):
            return True

        def chat_stream(self, *, messages, max_tokens, temperature, model=None):
            yield {"delta": "streaming ", "finish_reason": ""}
            yield {"delta": "result", "finish_reason": "stop"}

        def chat(self, *, messages, max_tokens, temperature, model=None):
            return {"choices": [{"message": {"content": "non-streamed"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(
        dispatch_mod,
        "_default_adapter_factory",
        lambda pid: _FakeStreamingAdapter(),
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
            "--anti-drift",
            "off",
            "--stream",
            "--max-agents",
            "3",
            "--json",
        ],
    )
    assert result.exit_code in (0, 4)
    out = result.stdout.strip()
    last_json = out[out.find("{") :]
    payload = json.loads(last_json)
    assert payload["streamed"] is True
