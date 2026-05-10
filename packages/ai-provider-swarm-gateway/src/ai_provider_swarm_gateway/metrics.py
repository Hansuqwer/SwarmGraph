"""Optional Prometheus metrics helpers.

The gateway base install must not require prometheus-client. Import failures are
handled by returning a no-op recorder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricsRecorder:
    """Thin wrapper around optional Prometheus collectors."""

    enabled: bool
    registry: Any = None
    requests_total: Any = None
    request_duration: Any = None
    quota_increment_total: Any = None
    audit_append_total: Any = None
    mcp_tool_rejects_total: Any = None

    def inc_request(self, *, method: str, endpoint: str, status: str, amount: int = 1) -> None:
        if self.requests_total is not None:
            self.requests_total.labels(method=method, endpoint=endpoint, status=status).inc(amount)

    def observe_request_duration(self, *, endpoint: str, seconds: float) -> None:
        if self.request_duration is not None:
            self.request_duration.labels(endpoint=endpoint).observe(seconds)

    def inc_quota(self, *, provider_id: str, amount: int = 1) -> None:
        if self.quota_increment_total is not None:
            self.quota_increment_total.labels(provider_id=provider_id).inc(amount)

    def inc_audit_append(self, *, backend: str, amount: int = 1) -> None:
        if self.audit_append_total is not None:
            self.audit_append_total.labels(backend=backend).inc(amount)

    def inc_mcp_reject(self, *, tool: str, amount: int = 1) -> None:
        if self.mcp_tool_rejects_total is not None:
            self.mcp_tool_rejects_total.labels(tool=tool).inc(amount)

    def render_latest(self) -> bytes:
        if not self.enabled or self.registry is None:
            return b""
        try:
            from prometheus_client import generate_latest  # type: ignore[import-not-found]
        except Exception:
            return b""
        return generate_latest(self.registry)


def build_metrics_recorder(*, registry: Any | None = None) -> MetricsRecorder:
    """Build collectors using a custom registry when provided.

    A custom registry keeps tests isolated and prevents duplicate registrations
    when service apps are created repeatedly.
    """
    try:
        from prometheus_client import (  # type: ignore[import-not-found]
            CollectorRegistry,
            Counter,
            Histogram,
        )
    except Exception:
        return MetricsRecorder(enabled=False)

    reg = registry or CollectorRegistry()
    return MetricsRecorder(
        enabled=True,
        registry=reg,
        requests_total=Counter(
            "swarmgraph_requests_total",
            "Total SwarmGraph service requests.",
            ["method", "endpoint", "status"],
            registry=reg,
        ),
        request_duration=Histogram(
            "swarmgraph_request_duration_seconds",
            "SwarmGraph service request duration in seconds.",
            ["endpoint"],
            registry=reg,
        ),
        quota_increment_total=Counter(
            "swarmgraph_quota_increment_total",
            "Total quota increments.",
            ["provider_id"],
            registry=reg,
        ),
        audit_append_total=Counter(
            "swarmgraph_audit_append_total",
            "Total audit append attempts.",
            ["backend"],
            registry=reg,
        ),
        mcp_tool_rejects_total=Counter(
            "swarmgraph_mcp_tool_rejects_total",
            "Total rejected MCP toolbox calls.",
            ["tool"],
            registry=reg,
        ),
    )


__all__ = ["MetricsRecorder", "build_metrics_recorder"]
