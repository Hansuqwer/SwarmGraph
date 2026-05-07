"""
AGENTS 11, 12 — Provider Model Specialist, Model Catalog Specialist
All provider metadata models — hardened Pydantic v2.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ── Shared Literals ──────────────────────────────────────────────────────────

Confidence = Literal["verified", "partially_verified", "unknown", "likely_changed"]
AuthType   = Literal["api_key", "oauth", "pat", "service_account", "manual", "unknown"]
Capability = Literal["chat", "vision", "embeddings", "audio", "image", "rerank", "tools", "code", "unknown"]
QuotaWindow = Literal["daily", "monthly", "trial", "unknown"]


# ── Link models ───────────────────────────────────────────────────────────────

class ProviderLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(..., min_length=1)
    url: str   = Field(..., min_length=1)

    @field_validator("url")
    @classmethod
    def _url_must_start_with_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"url must start with http:// or https://, got: {v!r}")
        return v


# ── Quota metadata ────────────────────────────────────────────────────────────

class ProviderQuota(BaseModel):
    """
    Verified free-tier quota data for one provider.
    confidence='unknown' means: do NOT treat as free without manual verification.
    """
    model_config = ConfigDict(extra="forbid")

    free_daily_usage:        str | None = None   # e.g. "1000 req/day" or None
    free_monthly_usage:      str | None = None   # e.g. "1B tokens/month"
    trial_credits:           str | None = None   # e.g. "$5 one-time (expires)"
    quota_reset_policy:      str | None = None   # e.g. "midnight UTC"
    requires_payment_method: bool | None = None
    api_access_available:    bool | None = None  # True = API, False = web only
    web_only_free_access:    bool | None = None  # True = web free but API costs money
    rate_limits:             str | None = None   # e.g. "30 RPM, 1000 RPD"
    confidence:              Confidence = "unknown"
    notes:                   list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unknown_limits_are_not_free(self) -> "ProviderQuota":
        """
        POLICY: If confidence is 'unknown', we cannot claim any specific free quota.
        This does NOT raise — it adds a warning note instead so routing can react.
        """
        if self.confidence == "unknown" and (
            self.free_daily_usage or self.free_monthly_usage
        ):
            if "UNVERIFIED" not in str(self.free_daily_usage or "") and \
               "UNVERIFIED" not in str(self.free_monthly_usage or ""):
                self.notes.append(
                    "WARNING: quota data present but confidence=unknown. "
                    "Do not treat as free without manual verification."
                )
        return self


# ── Provider info ─────────────────────────────────────────────────────────────

class ProviderInfo(BaseModel):
    """Full metadata for one AI provider. Loaded from providers.yaml."""
    model_config = ConfigDict(extra="forbid")

    provider_id:     str = Field(..., min_length=1)
    provider_name:   str = Field(..., min_length=1)
    website_url:     str
    signup_url:      str | None = None
    signin_url:      str | None = None
    api_docs_url:    str | None = None
    dashboard_url:   str | None = None
    models_url:      str | None = None
    auth_methods:    list[AuthType] = Field(default_factory=list)
    official_sdk:    list[str]     = Field(default_factory=list)
    supported_models: list[str]   = Field(default_factory=list)
    capabilities:    list[Capability] = Field(default_factory=list)
    quota:           ProviderQuota = Field(default_factory=ProviderQuota)
    terms_url:       str | None = None
    policy_notes:    list[str]  = Field(default_factory=list)
    source_links:    list[str]  = Field(default_factory=list)
    last_verified:   str | None = None   # ISO date string e.g. "2026-05-07"
    is_local:        bool = False         # True for Ollama, LM Studio etc.

    @field_validator("provider_id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("provider_id must not be empty")
        return v.lower().strip().replace(" ", "_")

    @field_validator("website_url", "signup_url", "signin_url",
                     "api_docs_url", "dashboard_url", "models_url",
                     "terms_url", mode="before")
    @classmethod
    def _url_or_none(cls, v: Any) -> Any:
        if v and isinstance(v, str) and not v.startswith(("http://", "https://")):
            return None  # treat malformed urls as absent, don't raise
        return v

    def is_api_free(self) -> bool:
        """True only if the provider is confirmed to have a free API tier."""
        return bool(
            self.quota.api_access_available
            and not self.quota.web_only_free_access
            and self.quota.confidence in ("verified", "partially_verified")
            and (self.quota.free_daily_usage or self.quota.free_monthly_usage or self.quota.trial_credits)
        )

    def is_web_only_free(self) -> bool:
        """True if free usage is web-only — API access requires payment."""
        return bool(self.quota.web_only_free_access)

    def signup_link(self) -> str | None:
        return self.signup_url

    def signin_link(self) -> str | None:
        return self.signin_url


# ── AI Model catalog ──────────────────────────────────────────────────────────

class AIModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id:           str
    model_id:              str
    display_name:          str
    capabilities:          list[Capability] = Field(default_factory=list)
    context_window_tokens: int | None = Field(default=None, ge=1)
    is_free_tier:          bool = False
    notes:                 list[str] = Field(default_factory=list)

    @field_validator("model_id", "provider_id")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model_id and provider_id must not be empty")
        return v.strip()
