"""Optional FastAPI service shell for hosted deployments."""

from __future__ import annotations

import os
from typing import Any

from .cli import _assert_production_profile
from .metrics import build_metrics_recorder


def _strict_ready_enabled() -> bool:
    return os.environ.get("AI_PROVIDER_GATEWAY_SERVICE_STRICT_READY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def create_app(*, strict_ready: bool | None = None) -> Any:
    """Create the optional FastAPI app.

    FastAPI and prometheus-client remain optional dependencies. Install with
    ``ai-provider-swarm-gateway[service]``.
    """
    try:
        from fastapi import FastAPI, status  # type: ignore[import-not-found]
        from fastapi.responses import JSONResponse  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError("FastAPI service requires ai-provider-swarm-gateway[service]") from exc

    app = FastAPI(title="SwarmGraph Gateway", version="0.1.0")
    recorder = build_metrics_recorder()
    app.state.metrics = recorder

    try:
        from prometheus_client import make_asgi_app  # type: ignore[import-not-found]

        if recorder.enabled and recorder.registry is not None:
            app.mount("/metrics", make_asgi_app(registry=recorder.registry))
    except Exception:
        app.state.metrics_enabled = False

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/readyz")
    async def readyz() -> dict[str, Any] | Any:
        strict = _strict_ready_enabled() if strict_ready is None else strict_ready
        if not strict:
            return {"ok": True, "strict": False}
        errors = _assert_production_profile(dict(os.environ))
        if errors:
            return JSONResponse(
                {"ok": False, "strict": True, "errors": errors},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return {"ok": True, "strict": True}

    return app


__all__ = ["create_app"]
