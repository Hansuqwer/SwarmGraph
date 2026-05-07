"""
AGENT 15 — Routing State Specialist
GatewayState and all related models — the LangGraph shared state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Capability = Literal["chat", "vision", "embeddings", "audio", "image", "rerank", "tools", "code", "unknown"]

_MAX_ATTEMPTS  = 20
_MAX_ERRORS    = 50
_MAX_AUDIT_LOG = 200


class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id:  str
    healthy:      bool = True
    latency_ms:   float | None = Field(default=None, ge=0.0)
    last_error:   str | None = None
    last_checked: datetime | None = None


class ProviderAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id:  str
    model_id:     str | None = None
    success:      bool = False
    error:        str | None = None
    started_at:   datetime | None = None
    finished_at:  datetime | None = None
    tokens_used:  int = Field(default=0, ge=0)


class RoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_provider_id:  str | None
    selected_model:        str | None
    reason:                str
    rejected_provider_ids: list[str] = Field(default_factory=list)
    policy_warnings:       list[str] = Field(default_factory=list)
    requires_user_action:  bool = False
    fallback_used:         bool = False


class GatewayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id:  str
    model_id:     str | None = None
    content:      str | None = None
    raw:          dict[str, Any] | None = None
    error:        str | None = None
    tokens_used:  int = Field(default=0, ge=0)
    latency_ms:   float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def _content_or_error(self) -> "GatewayResponse":
        if self.content is None and self.error is None:
            raise ValueError("GatewayResponse must have either content or error")
        return self


class GatewayState(BaseModel):
    """The canonical LangGraph state for the AI provider gateway workflow."""
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # Input
    user_prompt:           str = Field(..., min_length=1)
    requested_capability:  Capability | None = None
    preferred_provider_id: str | None = None
    allow_unknown_quota:   bool = False  # user opt-in to route to unknown-limit providers

    # Pipeline state
    candidate_providers:   list[str] = Field(default_factory=list)
    routing_decision:      RoutingDecision | None = None
    provider_response:     GatewayResponse | None = None

    # Tracking
    attempts:   list[ProviderAttempt] = Field(default_factory=list)
    errors:     list[str]             = Field(default_factory=list)
    audit_log:  list[str]             = Field(default_factory=list)

    # Policy
    policy_violations:  list[str] = Field(default_factory=list)
    is_safe_to_proceed: bool = True

    @model_validator(mode="after")
    def _cap_lists(self) -> "GatewayState":
        if len(self.attempts)   > _MAX_ATTEMPTS:
            self.attempts   = self.attempts[-_MAX_ATTEMPTS:]
        if len(self.errors)     > _MAX_ERRORS:
            self.errors     = self.errors[-_MAX_ERRORS:]
        if len(self.audit_log)  > _MAX_AUDIT_LOG:
            self.audit_log  = self.audit_log[-_MAX_AUDIT_LOG:]
        return self

    # ── Helpers ──────────────────────────────────────────────────────────────

    def log(self, msg: str) -> None:
        ts = datetime.utcnow().isoformat(timespec="seconds")
        self.audit_log = (self.audit_log + [f"[{ts}] {msg}"])[-_MAX_AUDIT_LOG:]

    def add_error(self, msg: str) -> None:
        self.errors = (self.errors + [msg])[-_MAX_ERRORS:]
        self.log(f"ERROR: {msg}")

    def add_policy_violation(self, msg: str) -> None:
        self.policy_violations = self.policy_violations + [msg]
        self.is_safe_to_proceed = False
        self.log(f"POLICY VIOLATION: {msg}")

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "GatewayState":
        return cls.model_validate(data)
