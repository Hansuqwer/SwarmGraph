"""Google Gemini adapter — requires GOOGLE_API_KEY env var."""

from __future__ import annotations

from ..models.state import GatewayResponse
from .base import ProviderAdapter


class GoogleAdapter(ProviderAdapter):
    provider_id = "google_gemini"
    default_model = "gemini-2.5-flash"

    def is_configured(self) -> bool:
        return bool(self._get_env("GOOGLE_API_KEY"))

    def call(self, prompt: str, model: str | None = None, **kwargs) -> GatewayResponse:
        if not self.is_configured():
            return self._not_configured_response()
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._get_env("GOOGLE_API_KEY"))
            m = genai.GenerativeModel(model or self.default_model)
            resp = m.generate_content(prompt)
            return GatewayResponse(
                provider_id=self.provider_id,
                model_id=model or self.default_model,
                content=resp.text,
            )
        except Exception as e:
            return self._error_response(str(e))
