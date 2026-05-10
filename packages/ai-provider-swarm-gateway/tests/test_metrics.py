from __future__ import annotations

import builtins

import pytest
from ai_provider_swarm_gateway.metrics import build_metrics_recorder


def test_metrics_noop_when_prometheus_unavailable(monkeypatch):
    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name.startswith("prometheus_client"):
            raise ModuleNotFoundError("prometheus_client")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)

    recorder = build_metrics_recorder()
    recorder.inc_request(method="GET", endpoint="/healthz", status="200")

    assert recorder.enabled is False
    assert recorder.render_latest() == b""


def test_metrics_increment_with_custom_registry():
    prometheus_client = pytest.importorskip("prometheus_client")

    registry = prometheus_client.CollectorRegistry()
    recorder = build_metrics_recorder(registry=registry)

    recorder.inc_request(method="GET", endpoint="/healthz", status="200")
    recorder.inc_quota(provider_id="openai")
    recorder.inc_audit_append(backend="jsonl")
    recorder.inc_mcp_reject(tool="run_flutter_analyze")

    assert registry.get_sample_value(
        "swarmgraph_requests_total",
        {"method": "GET", "endpoint": "/healthz", "status": "200"},
    ) == 1.0
    assert registry.get_sample_value(
        "swarmgraph_quota_increment_total",
        {"provider_id": "openai"},
    ) == 1.0
    assert registry.get_sample_value("swarmgraph_audit_append_total", {"backend": "jsonl"}) == 1.0
    assert registry.get_sample_value(
        "swarmgraph_mcp_tool_rejects_total",
        {"tool": "run_flutter_analyze"},
    ) == 1.0


def test_metrics_custom_registries_avoid_duplicate_registration():
    prometheus_client = pytest.importorskip("prometheus_client")

    first = build_metrics_recorder(registry=prometheus_client.CollectorRegistry())
    second = build_metrics_recorder(registry=prometheus_client.CollectorRegistry())

    first.inc_request(method="GET", endpoint="/healthz", status="200")
    second.inc_request(method="GET", endpoint="/healthz", status="200")

    assert first.enabled is True
    assert second.enabled is True
