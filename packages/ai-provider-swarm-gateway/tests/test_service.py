from __future__ import annotations

import builtins

import pytest
from ai_provider_swarm_gateway.service import create_app


def test_create_app_requires_fastapi(monkeypatch):
    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name.startswith("fastapi"):
            raise ModuleNotFoundError("fastapi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)

    with pytest.raises(RuntimeError, match=r"\[service\]"):
        create_app()


def test_healthz_ok():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_readyz_non_strict_ok(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.delenv("AI_PROVIDER_GATEWAY_SERVICE_STRICT_READY", raising=False)
    client = TestClient(create_app(strict_ready=False))

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "strict": False}


def test_readyz_strict_fails_missing_env(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    for key in (
        "AI_PROVIDER_GATEWAY_TENANT",
        "HIVE_SWARM_AUDIT_SECRET",
        "HIVE_SWARM_AUDIT_SIGNING_ENABLED",
        "HIVE_SWARM_AUDIT_FAIL_CLOSED",
        "HIVE_SWARM_AUDIT_LOG_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    client = TestClient(create_app(strict_ready=True))

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["ok"] is False


def test_readyz_strict_passes_with_env(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AI_PROVIDER_GATEWAY_TENANT", "tenant-1")
    monkeypatch.setenv("HIVE_SWARM_AUDIT_SECRET", "not-real")
    monkeypatch.setenv("HIVE_SWARM_AUDIT_SIGNING_ENABLED", "true")
    monkeypatch.setenv("HIVE_SWARM_AUDIT_FAIL_CLOSED", "true")
    monkeypatch.setenv(
        "HIVE_SWARM_AUDIT_LOG_PATH",
        "/var/lib/swarmgraph/audit/{tenant}/{swarm_id}.jsonl",
    )
    client = TestClient(create_app(strict_ready=True))

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "strict": True}


def test_metrics_endpoint_with_service_extra():
    pytest.importorskip("fastapi")
    pytest.importorskip("prometheus_client")
    from fastapi.testclient import TestClient

    client = TestClient(create_app())

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "swarmgraph_requests" in response.text
