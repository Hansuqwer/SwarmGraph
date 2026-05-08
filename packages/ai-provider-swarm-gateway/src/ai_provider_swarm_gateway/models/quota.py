from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QuotaWindow = Literal["daily", "monthly", "trial", "unknown"]


class QuotaLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window: QuotaWindow = "daily"
    max_requests: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=0)
    is_known: bool = False


class QuotaUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    window: QuotaWindow = "daily"
    used_requests: int = Field(default=0, ge=0)
    used_tokens: int = Field(default=0, ge=0)
    reset_at: datetime | None = None

    @model_validator(mode="after")
    def _no_negative(self) -> "QuotaUsage":
        if self.used_requests < 0 or self.used_tokens < 0:
            raise ValueError("quota usage cannot be negative")
        return self


class QuotaStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    limit: QuotaLimit
    usage: QuotaUsage
    is_exhausted: bool = False
    is_unknown: bool = False
    estimated_reset: datetime | None = None
    warning: str | None = None

    @model_validator(mode="after")
    def _flag_unknown(self) -> "QuotaStatus":
        if not self.limit.is_known:
            object.__setattr__(self, "is_unknown", True)
            object.__setattr__(
                self,
                "warning",
                "Quota limits unknown for this provider. Will not route as free unless user opts in to unknown providers.",
            )
        return self
