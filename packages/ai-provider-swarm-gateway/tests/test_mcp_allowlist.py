from __future__ import annotations

import json

import pytest
from ai_provider_swarm_gateway.mcp_allowlist import (
    ENV_VAR,
    WorkspaceNotAllowed,
    allowed_roots,
    enforce_allowed_path,
)
from ai_provider_swarm_gateway.mcptoolbox import run_flutter_analyze
from ai_provider_swarm_gateway.observability import counters_snapshot


def test_mcp_allowlist_unset_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_VAR, raising=False)

    with pytest.raises(WorkspaceNotAllowed):
        enforce_allowed_path(tmp_path)


def test_mcp_allowlist_allows_path_under_root(monkeypatch, tmp_path):
    app_root = tmp_path / "app"
    app_root.mkdir()
    monkeypatch.setenv(ENV_VAR, str(app_root))

    assert enforce_allowed_path(app_root / "lib" / "main.dart").is_relative_to(app_root)


def test_mcp_allowlist_rejects_traversal(monkeypatch, tmp_path):
    app_root = tmp_path / "app"
    other = tmp_path / "other"
    app_root.mkdir()
    other.mkdir()
    monkeypatch.setenv(ENV_VAR, str(app_root))

    with pytest.raises(WorkspaceNotAllowed):
        enforce_allowed_path(app_root / ".." / "other")


def test_mcp_allowlist_rejects_symlink_escape(monkeypatch, tmp_path):
    app_root = tmp_path / "app"
    other = tmp_path / "other"
    app_root.mkdir()
    other.mkdir()
    link = app_root / "link-out"
    link.symlink_to(other, target_is_directory=True)
    monkeypatch.setenv(ENV_VAR, str(app_root))

    with pytest.raises(WorkspaceNotAllowed):
        enforce_allowed_path(link)


def test_mcp_allowlist_parses_csv(monkeypatch, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv(ENV_VAR, f"{first},{second}")

    assert allowed_roots() == (first.resolve(), second.resolve())


def test_run_flutter_analyze_rejects_before_subprocess(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(ENV_VAR, raising=False)

    def _fail_run(*args, **kwargs):  # pragma: no cover - should not execute
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr("ai_provider_swarm_gateway.mcptoolbox.subprocess.run", _fail_run)
    result = run_flutter_analyze(str(tmp_path))

    assert result["ok"] is False
    assert result["error"] == "workspace_not_allowed"
    assert counters_snapshot()["mcp_tool_rejects_total"] >= 1
    log = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert log["event"] == "mcp.tool.reject"
