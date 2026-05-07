"""Tests for policy guardrails — all prohibited behaviors must be blocked."""
from __future__ import annotations
import pytest
from src.ai_provider_swarm_gateway.models.provider import ProviderInfo, ProviderQuota
from src.ai_provider_swarm_gateway.models.quota import QuotaUsage
from src.ai_provider_swarm_gateway.policy.guardrails import (
    validate_provider_policy, reject_quota_evasion, can_route_to_provider
)


def _make_provider(
    provider_id="test",
    api_access=True,
    web_only=False,
    requires_payment=False,
    confidence="verified",
    free_daily="100 req/day",
    is_local=False,
) -> ProviderInfo:
    return ProviderInfo(
        provider_id=provider_id,
        provider_name="Test Provider",
        website_url="https://test.com",
        is_local=is_local,
        quota=ProviderQuota(
            api_access_available=api_access,
            web_only_free_access=web_only,
            requires_payment_method=requires_payment,
            confidence=confidence,
            free_daily_usage=free_daily,
        ),
    )


class TestRejectQuotaEvasion:
    def test_account_rotation_blocked(self):
        violations = reject_quota_evasion({"account_rotation": True})
        assert len(violations) > 0
        assert any("POLICY VIOLATION" in v for v in violations)

    def test_bypass_quota_blocked(self):
        violations = reject_quota_evasion({"bypass_quota": "yes"})
        assert len(violations) > 0

    def test_multi_account_blocked(self):
        violations = reject_quota_evasion({"multi_account": "rotate"})
        assert len(violations) > 0

    def test_clean_request_passes(self):
        violations = reject_quota_evasion({"user_id": "abc123", "model": "gpt-4"})
        assert len(violations) == 0

    def test_policy_blocks_captcha_bypass(self):
        violations = reject_quota_evasion({"captcha_bypass": True})
        assert len(violations) > 0

    def test_policy_blocks_credential_harvest(self):
        violations = reject_quota_evasion({"credential_harvest": "auto"})
        assert len(violations) > 0


class TestValidateProviderPolicy:
    def test_web_only_generates_warning(self):
        provider = _make_provider(web_only=True)
        warnings = validate_provider_policy(provider)
        assert any("WEB-ONLY" in w for w in warnings)

    def test_unknown_confidence_generates_warning(self):
        provider = _make_provider(confidence="unknown")
        warnings = validate_provider_policy(provider)
        assert any("UNKNOWN" in w for w in warnings)

    def test_verified_free_no_critical_warning(self):
        provider = _make_provider(confidence="verified", api_access=True, web_only=False)
        warnings = validate_provider_policy(provider)
        # Should not have WEB-ONLY or UNKNOWN warnings
        assert not any("WEB-ONLY" in w for w in warnings)


class TestCanRouteToProvider:
    def test_no_credential_blocks_routing(self):
        provider = _make_provider()
        can, reasons = can_route_to_provider(provider, credential_available=False, usage=None)
        assert can is False
        assert any("credential" in r.lower() for r in reasons)

    def test_web_only_blocks_api_routing(self):
        provider = _make_provider(web_only=True)
        can, reasons = can_route_to_provider(provider, credential_available=True, usage=None)
        assert can is False
        assert any("WEB ACCESS" in r or "WEB-ONLY" in r for r in reasons)

    def test_unknown_quota_blocked_by_default(self):
        provider = _make_provider(confidence="unknown")
        can, reasons = can_route_to_provider(provider, credential_available=True, usage=None, allow_unknown_quota=False)
        assert can is False

    def test_unknown_quota_allowed_with_opt_in(self):
        provider = _make_provider(confidence="unknown")
        can, reasons = can_route_to_provider(provider, credential_available=True, usage=None, allow_unknown_quota=True)
        assert can is True

    def test_verified_free_routes_correctly(self):
        provider = _make_provider(confidence="verified", api_access=True, web_only=False)
        can, reasons = can_route_to_provider(provider, credential_available=True, usage=None)
        assert can is True

    def test_local_provider_no_credential_required(self):
        provider = _make_provider(is_local=True, confidence="verified")
        can, reasons = can_route_to_provider(provider, credential_available=False, usage=None)
        assert can is True

    def test_policy_blocks_web_only_as_api(self):
        """Critical: web-only free must never be routed as API free."""
        provider = _make_provider(web_only=True, api_access=True, confidence="verified")
        can, reasons = can_route_to_provider(provider, credential_available=True, usage=None)
        assert can is False
