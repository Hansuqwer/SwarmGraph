"""Anthropic adapter stub — requires ANTHROPIC_API_KEY env var."""

from __future__ import annotations
from ..models.state import GatewayResponse
from .base import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    provider_id = "anthropic"
    default_model = "claude-haiku-3-5"

    def is_configured(self) -> bool:
        return bool(self._get_env("ANTHROPIC_API_KEY"))

    def call(self, prompt: str, model: str | None = None, **kwargs) -> GatewayResponse:
        if not self.is_configured():
            return self._not_configured_response()
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._get_env("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model=model or self.default_model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text if resp.content else ""
            return GatewayResponse(
                provider_id=self.provider_id,
                model_id=resp.model,
                content=content,
                tokens_used=(resp.usage.input_tokens + resp.usage.output_tokens),
            )
        except Exception as e:
            return self._error_response(str(e))
