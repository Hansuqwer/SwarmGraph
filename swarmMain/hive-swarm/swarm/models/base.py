"""
AGENT 06 — Pydantic Base Model Specialist
Hardened BaseModel patterns, ConfigDict rules, serialization standards.
All models in this codebase inherit these conventions.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Standard ConfigDict presets
# ---------------------------------------------------------------------------

# For mutable top-level state objects (SwarmState, AgentState)
MUTABLE_CONFIG = ConfigDict(
    extra="forbid",
    validate_assignment=True,
    use_enum_values=True,
)

# For value objects / config that should never change after creation
FROZEN_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    use_enum_values=True,
)

# For results / output models that travel between nodes
RESULT_CONFIG = ConfigDict(
    extra="forbid",
    validate_assignment=False,   # results are set once
    use_enum_values=True,
)


# ---------------------------------------------------------------------------
# Shared serialization helpers
# ---------------------------------------------------------------------------

def stable_hash(text: str, length: int = 16) -> str:
    """Return a stable hex digest of any string (used for objective_hash, task_hash)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def now_ts() -> float:
    """Current UNIX timestamp. Used as Field default_factory."""
    return time.time()


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------

class HardenedModel(BaseModel):
    """
    Base for all mutable swarm models.
    - extra='forbid'  → unknown fields raise ValidationError
    - validate_assignment → attribute mutations are validated
    """
    model_config = MUTABLE_CONFIG

    def to_json_dict(self) -> dict[str, Any]:
        """JSON-safe dict for LangGraph state payloads and checkpoint storage."""
        return self.model_dump(mode="json")

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "HardenedModel":
        """Reconstruct from a JSON-safe dict (checkpoint restore)."""
        return cls.model_validate(data)


class FrozenModel(BaseModel):
    """
    Base for immutable configuration / value objects.
    - extra='forbid'
    - frozen=True → any mutation attempt raises ValidationError
    """
    model_config = FROZEN_CONFIG
