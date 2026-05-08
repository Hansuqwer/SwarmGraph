"""Bounded-list helpers (F-W6A consolidation; replaces 3 duplications of `_cap_lists`)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CappedListConfig:
    """How to cap a list when it exceeds max_len."""
    max_len: int
    keep_strategy: str = "tail"   # "tail" | "head_plus_tail" | "head"

    def __post_init__(self) -> None:
        if self.max_len < 1:
            raise ValueError("max_len must be >= 1")
        if self.keep_strategy not in ("tail", "head_plus_tail", "head"):
            raise ValueError(f"unknown keep_strategy: {self.keep_strategy!r}")


def cap_list(items: list[T], cfg: CappedListConfig) -> list[T]:
    """Cap `items` per cfg. Pure function — does not mutate."""
    n = len(items)
    if n <= cfg.max_len:
        return items
    if cfg.keep_strategy == "tail":
        return items[-cfg.max_len:]
    if cfg.keep_strategy == "head":
        return items[: cfg.max_len]
    # head_plus_tail: keep first 1 + last (max_len - 1)
    if cfg.max_len < 2:
        return items[: cfg.max_len]
    return items[:1] + items[-(cfg.max_len - 1):]


def bounded_list_validator(
    field_name: str,
    cfg: CappedListConfig,
) -> Callable[[list[T]], list[T]]:
    """Build a Pydantic v2 field validator function that caps a list.

    Usage:
        from pydantic import BaseModel, field_validator
        from swarm_shared.bounded_list import bounded_list_validator, CappedListConfig

        _HISTORY_CFG = CappedListConfig(max_len=500, keep_strategy="head_plus_tail")

        class State(BaseModel):
            history: list[dict] = Field(default_factory=list)

            _validate_history = field_validator("history")(
                bounded_list_validator("history", _HISTORY_CFG)
            )
    """

    def _validator(value: list[T]) -> list[T]:
        if not isinstance(value, list):
            raise TypeError(f"{field_name} must be a list")
        return cap_list(value, cfg)

    return _validator


# Direct convenience: most callers just want cap_list in a model_validator
__all__ = ["CappedListConfig", "cap_list", "bounded_list_validator"]
