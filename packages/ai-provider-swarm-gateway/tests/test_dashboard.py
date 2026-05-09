from __future__ import annotations

import builtins
import json
from pathlib import Path

from ai_provider_swarm_gateway.cli import app
from ai_provider_swarm_gateway.dashboard import build_agreement_plot, load_consensus_history
from typer.testing import CliRunner

runner = CliRunner()


def test_load_consensus_history_skips_bad_lines(tmp_path: Path):
    path = tmp_path / "consensus_history.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"swarm_id": "s1", "agreement": 0.5, "protocol": "raft"}),
                "not-json",
                json.dumps(["not", "dict"]),
                json.dumps({"swarm_id": "s2", "agreement_fraction": 0.75, "protocol": "bft"}),
            ]
        ),
        encoding="utf-8",
    )

    records = load_consensus_history(path)

    assert [record["swarm_id"] for record in records] == ["s1", "s2"]


def test_load_consensus_history_limits_to_last_n(tmp_path: Path):
    path = tmp_path / "consensus_history.jsonl"
    path.write_text(
        "\n".join(json.dumps({"swarm_id": f"s{i}", "agreement": i / 10}) for i in range(5)),
        encoding="utf-8",
    )

    records = load_consensus_history(path, limit=2)

    assert [record["swarm_id"] for record in records] == ["s3", "s4"]


def test_build_agreement_plot_returns_text():
    plot = build_agreement_plot(
        [
            {"swarm_id": "s1", "agreement": 0.25},
            {"swarm_id": "s2", "agreement_fraction": 0.75},
        ]
    )

    assert "Consensus Agreement Trend" in plot


def test_dashboard_command_missing_optional_deps_prints_hint(monkeypatch):
    import ai_provider_swarm_gateway.dashboard as dashboard_mod

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("textual"):
            raise ImportError("no textual")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(dashboard_mod, "show_dashboard", dashboard_mod.show_dashboard)

    result = runner.invoke(app, ["dashboard"])

    assert result.exit_code == 1
    out = (result.stdout + (result.stderr or "")).replace("\n", " ")
    assert "uv sync --extra tui" in out and "--dev" in out


def test_dashboard_command_calls_show_dashboard(monkeypatch, tmp_path: Path):
    called = {}

    def fake_show_dashboard(*, history_path=None, storage=None):
        called["history_path"] = history_path
        called["storage"] = storage

    monkeypatch.setattr("ai_provider_swarm_gateway.dashboard.show_dashboard", fake_show_dashboard)
    history_path = tmp_path / "history.jsonl"
    storage = tmp_path / "usage.json"

    result = runner.invoke(
        app,
        [
            "dashboard",
            "--history-path",
            str(history_path),
            "--storage",
            str(storage),
        ],
    )

    assert result.exit_code == 0
    assert called == {"history_path": history_path, "storage": storage}
