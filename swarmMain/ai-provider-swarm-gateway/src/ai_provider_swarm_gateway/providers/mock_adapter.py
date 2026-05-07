"""
Mock provider adapter — deterministic, simulates quota, supports failure injection.
Used in all tests. No credentials required.
"""
from __future__ import annotations

from ..models.state import GatewayResponse
from .base import ProviderAdapter


class MockAdapter(ProviderAdapter):
    """
    Deterministic mock adapter for testing.
    - Always configured (no credentials needed)
    - Returns predictable response
    - Supports simulated failure injection
    - Simulates token usage
    """

    provider_id   = "mock"
    default_model = "mock-model-v1"

    def __init__(
        self,
        simulate_failure: bool = False,
        failure_message: str = "Simulated provider failure",
        response_prefix: str = "[MOCK]",
    ) -> None:
        self.simulate_failure = simulate_failure
        self.failure_message  = failure_message
        self.response_prefix  = response_prefix
        self._call_count      = 0

    def is_configured(self) -> bool:
        return True

    def call(self, prompt: str, model: str | None = None, **kwargs) -> GatewayResponse:
        self._call_count += 1
        if self.simulate_failure:
            return self._error_response(self.failure_message)
        response_text = (
            f"{self.response_prefix} Response to: '{prompt[:50]}...' "
            f"(call #{self._call_count})"
        )
        return GatewayResponse(
            provider_id=self.provider_id,
            model_id=model or self.default_model,
            content=response_text,
            tokens_used=len(prompt.split()) * 2,  # rough estimate
            latency_ms=42.0,
        )

    def reset(self) -> None:
        self._call_count = 0
