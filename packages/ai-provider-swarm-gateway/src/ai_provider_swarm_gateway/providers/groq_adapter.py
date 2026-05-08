"""Groq adapter — requires GROQ_API_KEY env var. OpenAI-compatible."""
from __future__ import annotations
from ..models.state import GatewayResponse
from .base import ProviderAdapter

class GroqAdapter(ProviderAdapter):
    provider_id   = "groq"
    default_model = "llama-3.3-70b-versatile"

    def is_configured(self) -> bool:
        return bool(self._get_env("GROQ_API_KEY"))

    def call(self, prompt: str, model: str | None = None, **kwargs) -> GatewayResponse:
        if not self.is_configured():
            return self._not_configured_response()
        try:
            from groq import Groq
            client = Groq(api_key=self._get_env("GROQ_API_KEY"))
            resp = client.chat.completions.create(
                model=model or self.default_model,
                messages=[{"role": "user", "content": prompt}],
            )
            return GatewayResponse(
                provider_id=self.provider_id,
                model_id=resp.model,
                content=resp.choices[0].message.content,
                tokens_used=(resp.usage.total_tokens if resp.usage else 0),
            )
        except Exception as e:
            return self._error_response(str(e))
