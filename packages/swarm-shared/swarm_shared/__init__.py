"""swarm-shared: cross-project primitives.

Owners: A12 + A20 + A26 (per fix_plan.md F-W6A).
Resolves duplications: RedactingCheckpointer (×2), atomic_write (×2),
_cap_lists model_validator (×2), stable_hash (×2 with drift).
"""

from .atomic_write import atomic_write_json, atomic_write_text
from .bounded_list import CappedListConfig, bounded_list_validator
from .checkpointing import BaseRedactingCheckpointer
from .hashing import full_sha256, stable_hash
from .redaction import (
    SECRET_PATTERNS,
    Redactor,
    redact_obj,
    redact_patch,
    redact_text,
)
from .time import monotonic_ts, now_ts

__all__ = [
    "stable_hash",
    "full_sha256",
    "now_ts",
    "monotonic_ts",
    "atomic_write_json",
    "atomic_write_text",
    "bounded_list_validator",
    "CappedListConfig",
    "SECRET_PATTERNS",
    "redact_text",
    "redact_patch",
    "redact_obj",
    "Redactor",
    "BaseRedactingCheckpointer",
]

__version__ = "0.1.0"
