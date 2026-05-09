from __future__ import annotations

import json

from ai_provider_swarm_gateway.cli import app
from ai_provider_swarm_gateway.mcp_allowlist import ENV_VAR
from ai_provider_swarm_gateway.mcptoolbox import flutter_project_summary, toolbox_manifest
from typer.testing import CliRunner

runner = CliRunner()


def test_mcp_toolbox_help_is_registered():
    result = runner.invoke(app, ["mcp-toolbox", "--help"])

    assert result.exit_code == 0
    assert "Optional MCP toolbox" in result.stdout


def test_mcp_toolbox_tools_json():
    result = runner.invoke(app, ["mcp-toolbox", "tools", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["name"] == "swarmgraph-mcptoolbox"
    assert any(tool["name"] == "flutter_project_summary" for tool in payload["tools"])


def test_mcp_toolbox_config_includes_dart_and_swarmgraph():
    result = runner.invoke(app, ["mcp-toolbox", "config"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mcpServers"]["dart"]["args"] == ["mcp-server"]
    assert payload["mcpServers"]["swarmgraph-mcptoolbox"]["args"] == [
        "mcp-toolbox",
        "serve",
    ]


def test_mcp_toolbox_manifest_and_project_summary(monkeypatch, tmp_path):
    (tmp_path / "pubspec.yaml").write_text("name: app\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "main.dart").write_text("void main() {}\n")
    monkeypatch.setenv(ENV_VAR, str(tmp_path))

    manifest = toolbox_manifest()
    summary = flutter_project_summary(str(tmp_path))

    assert manifest["install_extra"] == "ai-provider-swarm-gateway[flutter]"
    assert manifest["compatibility_extras"] == ["mcp-toolbox"]
    assert summary["pubspec_exists"] is True
    assert summary["dart_files"] == 1


def test_mcp_toolbox_serve_error_mentions_flutter_first(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name.startswith("mcp"):
            raise ModuleNotFoundError("mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    result = runner.invoke(app, ["mcp-toolbox", "serve"])

    assert result.exit_code != 0
    assert "ai-provider-swarm-gateway[flutter]" in result.output
    assert "legacy [mcp-toolbox]" in result.output
