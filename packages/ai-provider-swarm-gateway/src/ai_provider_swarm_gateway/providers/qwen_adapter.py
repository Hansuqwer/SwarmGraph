"""Qwen/Alibaba Cloud adapter stub — requires QWEN_API_KEY."""

from __future__ import annotations

from ..models.state import GatewayResponse
from .base import ProviderAdapter


class QwenAdapter(ProviderAdapter):
    provider_id = "qwen"
    default_model = "qwen-turbo"
    _base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    def is_configured(self) -> bool:
        return bool(self._get_env("QWEN_API_KEY"))

    def call(self, prompt: str, model: str | None = None, **kwargs) -> GatewayResponse:
        if not self.is_configured():
            return self._not_configured_response()
        try:
            import openai

            client = openai.OpenAI(api_key=self._get_env("QWEN_API_KEY"), base_url=self._base_url)
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
