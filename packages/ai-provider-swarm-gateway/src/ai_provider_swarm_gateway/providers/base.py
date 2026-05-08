"""
AGENT 21 — Provider Call Node Specialist
Base provider adapter interface. All adapters inherit this.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from ..models.state import GatewayResponse


class ProviderAdapter(ABC):
    """Abstract base for all provider adapters."""

    provider_id: str = "unknown"
    default_model: str = "unknown"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required credentials are present in environment."""
        ...

    @abstractmethod
    def call(self, prompt: str, model: str | None = None, **kwargs) -> GatewayResponse:
        """Make an inference call. Never raises — returns GatewayResponse with error field."""
        ...

    def _get_env(self, var_name: str) -> str | None:
        """Safely retrieve env var. Never logs the value."""
        return os.environ.get(var_name)

    def _not_configured_response(self) -> GatewayResponse:
        return GatewayResponse(
            provider_id=self.provider_id,
            model_id=self.default_model,
            content=None,
            error=(
                f"Provider '{self.provider_id}' is not configured. "
                f"Set the required environment variable and retry."
            ),
        )

    def _error_response(self, error: str) -> GatewayResponse:
        return GatewayResponse(
            provider_id=self.provider_id,
            model_id=self.default_model,
            content=None,
            error=error,
        )
