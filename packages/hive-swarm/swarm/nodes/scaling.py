"""Resource-aware scaling node."""
from __future__ import annotations

from typing import Any

from ..models.state import SwarmState


def _available_ram_mb() -> int | None:
    try:
        import psutil  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        return int(psutil.virtual_memory().available / (1024 * 1024))
    except Exception:
        return None


def scaling_node(state: dict[str, Any]) -> dict[str, Any]:
    """Apply a runtime agent cap without mutating immutable SwarmConfig."""
    swarm = SwarmState.model_validate(state)
    if not swarm.config.auto_scale_agents:
        return swarm.to_json_dict()

    available_mb = _available_ram_mb()
    if available_mb is None:
        swarm.runtime_metadata.pop("applied_agent_cap", None)
        return swarm.to_json_dict()

    per_agent = swarm.config.scaling_ram_per_agent_mb
    suggested_cap = max(1, min(swarm.config.max_agents, available_mb // per_agent))
    swarm.runtime_metadata["available_ram_mb"] = available_mb
    swarm.runtime_metadata["applied_agent_cap"] = suggested_cap
    if suggested_cap < swarm.config.max_agents:
        swarm.append_history(
            "scaling_cap",
            {
                "available_ram_mb": available_mb,
                "max_agents": swarm.config.max_agents,
                "applied_agent_cap": suggested_cap,
            },
        )
    swarm.touch()
    return swarm.to_json_dict()


__all__ = ["scaling_node"]
