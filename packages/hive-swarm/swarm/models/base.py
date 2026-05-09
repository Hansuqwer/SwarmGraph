"""Hardened BaseModel patterns (patched).

F-06A: revalidate_instances explicit
F-06B: monotonic_ts() added
F-06C: stable_hash docstring caveat
F-W6 : delegates hashing/time helpers to swarm_shared (preserving local re-exports
       for backwards compatibility).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

# Delegate to swarm-shared (W6 consolidation) — preserve local names.
from swarm_shared.hashing import full_sha256, stable_hash
from swarm_shared.time import monotonic_ts, now_ts

# ── ConfigDict presets ─────────────────────────────────────────────────────

# For mutable top-level state objects (SwarmState, AgentState)
MUTABLE_CONFIG = ConfigDict(
    extra="forbid",
    validate_assignment=True,
    use_enum_values=True,
    revalidate_instances="never",  # F-06A: explicit (was implicit)
)

# For value objects / config that should never change after creation
FROZEN_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    use_enum_values=True,
    revalidate_instances="never",
)

# For results / outputs that travel between nodes (set-once semantics)
RESULT_CONFIG = ConfigDict(
    extra="forbid",
    validate_assignment=False,
    use_enum_values=True,
    revalidate_instances="never",
)


# ── Base classes ───────────────────────────────────────────────────────────


class HardenedModel(BaseModel):
    """Base for all mutable swarm models.

    - extra='forbid' → unknown fields raise ValidationError
    - validate_assignment → attribute mutations are validated
    """

    model_config = MUTABLE_CONFIG

    def to_json_dict(self) -> dict[str, Any]:
        """JSON-safe dict for LangGraph state payloads and checkpoint storage."""
        return self.model_dump(mode="json")

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> HardenedModel:
        """Reconstruct from a JSON-safe dict (checkpoint restore)."""
        return cls.model_validate(data)


class FrozenModel(BaseModel):
    """Base for immutable configuration / value objects.

    - extra='forbid'
    - frozen=True → any mutation attempt raises ValidationError
    """

    model_config = FROZEN_CONFIG


__all__ = [
    "MUTABLE_CONFIG",
    "FROZEN_CONFIG",
    "RESULT_CONFIG",
    "HardenedModel",
    "FrozenModel",
    "stable_hash",
    "full_sha256",
    "now_ts",
    "monotonic_ts",
]
