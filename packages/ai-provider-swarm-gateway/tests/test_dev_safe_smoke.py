from __future__ import annotations

import json

from ai_provider_swarm_gateway.cli import app
from ai_provider_swarm_gateway.mcp_allowlist import ENV_VAR
from ai_provider_swarm_gateway.mcptoolbox import flutter_project_summary
from ai_provider_swarm_gateway.quota.pool import SecretStore, create_vault_key
from typer.testing import CliRunner

runner = CliRunner()


def test_dev_safe_config_smoke(monkeypatch, tmp_path):
    app_root = tmp_path / "fixture_app"
    (app_root / "lib").mkdir(parents=True)
    (app_root / "pubspec.yaml").write_text("name: fixture_app\n", encoding="utf-8")
    (app_root / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(app_root))
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_STATE_DIR", str(tmp_path))

    tools = runner.invoke(app, ["mcp-toolbox", "tools", "--json"])
    assert tools.exit_code == 0
    payload = json.loads(tools.stdout)
    assert any(tool["name"] == "run_flutter_analyze" for tool in payload["tools"])

    summary = flutter_project_summary(str(app_root))
    assert summary["pubspec_exists"] is True
    assert summary["dart_files"] == 1

    key_path = tmp_path / "vault.key"
    vault_path = tmp_path / "secrets.json.enc"
    create_vault_key(key_path)
    store = SecretStore(vault_path, key_path=key_path)
    store.add_key("9router", "dev", "test-secret")
    assert SecretStore(vault_path, key_path=key_path).to_summary() == {"9router": ["dev"]}
