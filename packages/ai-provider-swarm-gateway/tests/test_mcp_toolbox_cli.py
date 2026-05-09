from __future__ import annotations

import json

from ai_provider_swarm_gateway.cli import app
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


def test_mcp_toolbox_manifest_and_project_summary(tmp_path):
    (tmp_path / "pubspec.yaml").write_text("name: app\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "main.dart").write_text("void main() {}\n")

    manifest = toolbox_manifest()
    summary = flutter_project_summary(str(tmp_path))

    assert manifest["install_extra"] == "ai-provider-swarm-gateway[mcp-toolbox]"
    assert summary["pubspec_exists"] is True
    assert summary["dart_files"] == 1
