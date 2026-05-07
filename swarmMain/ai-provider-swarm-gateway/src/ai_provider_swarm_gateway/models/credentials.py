"""
AGENT 14 — Credential Config Specialist
Safe credential references — env var names only, never raw secrets.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AuthType    = Literal["api_key", "oauth", "pat", "service_account", "manual", "unknown"]
SecretBackend = Literal["env", "dotenv", "vault", "none"]


class ProviderCredentialRef(BaseModel):
    """Reference to a credential by environment variable name — never stores the secret."""
    model_config = ConfigDict(extra="forbid")

    provider_id:        str
    credential_env_var: str   # e.g. "GROQ_API_KEY" — NOT the key value itself
    auth_type:          AuthType = "api_key"

    @field_validator("credential_env_var")
    @classmethod
    def _must_be_env_var_name(cls, v: str) -> str:
        if v.startswith("sk-") or v.startswith("Bearer ") or len(v) > 80:
            raise ValueError(
                "credential_env_var must be an environment variable NAME "
                "(e.g. 'GROQ_API_KEY'), not the raw secret value."
            )
        if not v.isupper() and not all(c.isalpha() or c == "_" for c in v):
            # Allow UPPER_SNAKE_CASE, but warn
            pass
        return v.strip()

    @field_validator("provider_id")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("provider_id must not be empty")
        return v.strip()


class CredentialStorageConfig(BaseModel):
    """How credentials are stored and loaded."""
    model_config = ConfigDict(extra="forbid")

    backend:      SecretBackend = "dotenv"
    dotenv_path:  str = ".env"
    vault_addr:   str | None = None
    vault_path:   str | None = None


class AuthStatus(BaseModel):
    """Runtime auth status for one provider."""
    model_config = ConfigDict(extra="forbid")

    provider_id:        str
    is_configured:      bool = False
    env_var_present:    bool = False
    auth_type:          AuthType = "unknown"
    error_message:      str | None = None
