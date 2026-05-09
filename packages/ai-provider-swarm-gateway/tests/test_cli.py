"""CLI smoke tests — verifies entry point + quota commands work end-to-end."""

import json
import re
from pathlib import Path

import pytest
from ai_provider_swarm_gateway.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "AI Provider Swarm Gateway" in result.stdout


def test_version_lists_packages():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "ai-provider-swarm-gateway" in result.stdout
    assert "swarm-shared" in result.stdout


def test_quota_show_empty(tmp_path: Path):
    fp = tmp_path / "usage.json"
    result = runner.invoke(app, ["quota", "show", "--storage", str(fp)])
    assert result.exit_code == 0
    assert "no usage recorded" in result.stdout.lower() or "Quota usage" in result.stdout


def test_quota_increment_persists(tmp_path: Path):
    fp = tmp_path / "usage.json"
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
            "120",
            "--storage",
            str(fp),
        ],
    )
    assert result.exit_code == 0
    assert "requests=5" in result.stdout
    assert "tokens=120" in result.stdout
    # File now exists and is valid JSON
    data = json.loads(fp.read_text())
    assert "openai:daily" in data
    assert data["openai:daily"]["used_requests"] == 5
    assert data["openai:daily"]["used_tokens"] == 120


def test_quota_show_after_increment_json(tmp_path: Path):
    fp = tmp_path / "usage.json"
    runner.invoke(
        app,
        ["quota", "increment", "--provider", "anthropic", "--tokens", "999", "--storage", str(fp)],
    )
    result = runner.invoke(app, ["quota", "show", "--storage", str(fp), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert any(row["provider"] == "anthropic" for row in payload)


def test_quota_reset_skips_confirm(tmp_path: Path):
    fp = tmp_path / "usage.json"
    runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai", "--requests", "10", "--storage", str(fp)],
    )
    result = runner.invoke(
        app,
        ["quota", "reset", "--provider", "openai", "--yes", "--storage", str(fp)],
    )
    assert result.exit_code == 0
    assert "reset" in result.stdout.lower()
    # Counter reset to 0
    after = runner.invoke(
        app, ["quota", "show", "--provider", "openai", "--storage", str(fp), "--json"]
    )
    payload = json.loads(after.stdout)
    assert payload[0]["used_requests"] == 0


def test_quota_increment_rejects_negative(tmp_path: Path):
    fp = tmp_path / "usage.json"
    result = runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai", "--requests", "-1", "--storage", str(fp)],
    )
    # Typer enforces min=0 → non-zero exit
    assert result.exit_code != 0


def test_quota_increment_zero_zero_rejected(tmp_path: Path):
    fp = tmp_path / "usage.json"
    result = runner.invoke(
        app,
        ["quota", "increment", "--provider", "openai", "--storage", str(fp)],
    )
    assert result.exit_code == 2
    assert "Nothing to increment" in result.stdout or "Nothing to increment" in (
        result.stderr or ""
    )


def test_providers_list_reads_registry():
    """Vendored registry is rendered when shipped."""
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0
    out = result.stdout + (result.stderr or "")
    assert "google_gemini" in out


def test_route_runs_or_reports_no_selection():
    """`route` invokes the gateway graph."""
    result = runner.invoke(app, ["route", "--prompt", "hello world"])
    assert result.exit_code in (0, 4)
    out = result.stdout + (result.stderr or "")
    assert "route" in out.lower() or "selected" in out.lower() or "no provider" in out.lower()


def test_storage_env_override(tmp_path: Path, monkeypatch):
    fp = tmp_path / "via-env.json"
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_USAGE_PATH", str(fp))
    result = runner.invoke(
        app,
        ["quota", "increment", "--provider", "groq", "--tokens", "1"],
    )
    assert result.exit_code == 0
    assert fp.exists()
