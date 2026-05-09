from __future__ import annotations

import json

from ai_provider_swarm_gateway.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_profile_production_check_fails_when_missing_env(monkeypatch):
    for key in (
        "AI_PROVIDER_GATEWAY_TENANT",
        "HIVE_SWARM_AUDIT_SECRET",
        "HIVE_SWARM_AUDIT_SIGNING_ENABLED",
        "HIVE_SWARM_AUDIT_FAIL_CLOSED",
        "HIVE_SWARM_AUDIT_LOG_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    result = runner.invoke(app, ["profile", "production", "--check", "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "AI_PROVIDER_GATEWAY_TENANT is required" in payload["errors"]


def test_profile_production_check_passes_with_full_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_TENANT", "tenant-1")
    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", "not-real-but-non-empty")
    monkeypatch.setenv("HIVE_SWARM_AUDIT_SIGNING_ENABLED", "true")
    monkeypatch.setenv("HIVE_SWARM_AUDIT_FAIL_CLOSED", "true")
    monkeypatch.setenv(
        "HIVE_SWARM_AUDIT_LOG_PATH",
        "/var/lib/swarmgraph/audit/{tenant}/{swarm_id}.jsonl",
    )

    result = runner.invoke(app, ["profile", "production", "--check", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True}
