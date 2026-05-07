"""Tests for Pydantic v2 model correctness."""
from __future__ import annotations
import pytest
from datetime import datetime
from pydantic import ValidationError
from src.ai_provider_swarm_gateway.models.provider import ProviderInfo, ProviderQuota
from src.ai_provider_swarm_gateway.models.state import GatewayState, GatewayResponse
from src.ai_provider_swarm_gateway.models.quota import QuotaUsage
from src.ai_provider_swarm_gateway.models.credentials import ProviderCredentialRef


class TestProviderInfo:
    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            ProviderInfo(provider_id="x", provider_name="X", website_url="https://x.com", unknown_field="evil")

    def test_provider_id_slugified(self):
        p = ProviderInfo(provider_id="My Provider", provider_name="X", website_url="https://x.com")
        assert p.provider_id == "my_provider"

    def test_is_api_free_verified(self):
        p = ProviderInfo(
            provider_id="test", provider_name="T", website_url="https://t.com",
            quota=ProviderQuota(api_access_available=True, web_only_free_access=False,
                                free_daily_usage="100/day", confidence="verified"),
        )
        assert p.is_api_free() is True

    def test_is_api_free_unknown_is_false(self):
        p = ProviderInfo(
            provider_id="test2", provider_name="T2", website_url="https://t2.com",
            quota=ProviderQuota(api_access_available=True, free_daily_usage="100/day", confidence="unknown"),
        )
        assert p.is_api_free() is False

    def test_web_only_not_api_free(self):
        p = ProviderInfo(
            provider_id="test3", provider_name="T3", website_url="https://t3.com",
            quota=ProviderQuota(web_only_free_access=True, confidence="verified"),
        )
        assert p.is_web_only_free() is True
        assert p.is_api_free() is False


class TestGatewayState:
    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            GatewayState(user_prompt="hello", evil_field="bad")

    def test_empty_prompt_valid_at_model_level(self):
        # GatewayState accepts empty but intake_node will reject
        with pytest.raises(ValidationError):
            GatewayState(user_prompt="")

    def test_audit_log_bounded(self):
        from src.ai_provider_swarm_gateway.models.state import _MAX_AUDIT_LOG
        big_log = [f"entry {i}" for i in range(_MAX_AUDIT_LOG + 50)]
        s = GatewayState(user_prompt="test", audit_log=big_log)
        assert len(s.audit_log) <= _MAX_AUDIT_LOG

    def test_round_trip_json(self):
        s = GatewayState(user_prompt="hello world", requested_capability="chat")
        restored = GatewayState.from_json_dict(s.to_json_dict())
        assert restored.user_prompt == s.user_prompt

    def test_gateway_response_requires_content_or_error(self):
        with pytest.raises(ValidationError, match="content or error"):
            GatewayResponse(provider_id="x", content=None, error=None)

    def test_gateway_response_with_content(self):
        r = GatewayResponse(provider_id="mock", content="hello")
        assert r.content == "hello"
        assert r.error is None


class TestQuotaUsage:
    def test_negative_usage_rejected(self):
        with pytest.raises(ValidationError, match="negative"):
            QuotaUsage(provider_id="x", used_requests=-1, used_tokens=0)

    def test_zero_usage_valid(self):
        u = QuotaUsage(provider_id="x", used_requests=0, used_tokens=0)
        assert u.used_requests == 0


class TestCredentialRef:
    def test_raw_secret_rejected(self):
        with pytest.raises(ValidationError, match="variable NAME"):
            ProviderCredentialRef(provider_id="x", credential_env_var="sk-abc123verylongsecret", auth_type="api_key")

    def test_env_var_name_accepted(self):
        c = ProviderCredentialRef(provider_id="groq", credential_env_var="GROQ_API_KEY", auth_type="api_key")
        assert c.credential_env_var == "GROQ_API_KEY"


class TestProviderQuota:
    def test_unknown_with_quota_adds_warning_note(self):
        q = ProviderQuota(confidence="unknown", free_daily_usage="999 req/day")
        assert any("WARNING" in n for n in q.notes)
