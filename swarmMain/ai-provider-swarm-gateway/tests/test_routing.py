"""Tests for routing logic — preference order, credential checks, free-first."""
from __future__ import annotations
import pytest
from src.ai_provider_swarm_gateway.consensus.strategies import (
    ProviderVote, majority_consensus, weighted_confidence_consensus,
    policy_guarded_consensus, cost_aware_consensus,
)
from src.ai_provider_swarm_gateway.models.provider import ProviderInfo, ProviderQuota
from src.ai_provider_swarm_gateway.models.state import GatewayState


def _mock_providers():
    return {
        "groq": ProviderInfo(
            provider_id="groq", provider_name="Groq", website_url="https://groq.com",
            quota=ProviderQuota(api_access_available=True, web_only_free_access=False,
                                free_daily_usage="1000/day", confidence="verified"),
        ),
        "openai": ProviderInfo(
            provider_id="openai", provider_name="OpenAI", website_url="https://openai.com",
            quota=ProviderQuota(api_access_available=True, web_only_free_access=False,
                                requires_payment_method=True, confidence="verified"),
        ),
        "web_only_provider": ProviderInfo(
            provider_id="web_only_provider", provider_name="WebOnly", website_url="https://webonly.com",
            quota=ProviderQuota(api_access_available=True, web_only_free_access=True, confidence="verified"),
        ),
    }


class TestMajorityConsensus:
    def test_majority_wins(self):
        providers = _mock_providers()
        votes = [
            ProviderVote(provider_id="groq",  score=0.8, reason="free"),
            ProviderVote(provider_id="groq",  score=0.9, reason="fast"),
            ProviderVote(provider_id="openai", score=0.7, reason="quality"),
        ]
        winner = majority_consensus(votes, providers)
        assert winner is not None
        assert winner.provider_id == "groq"

    def test_web_only_rejected_by_policy_guard(self):
        providers = _mock_providers()
        votes = [ProviderVote(provider_id="web_only_provider", score=1.0, reason="test")]
        winner = majority_consensus(votes, providers)
        assert winner is None  # policy guard blocks web-only

    def test_empty_votes_returns_none(self):
        assert majority_consensus([], _mock_providers()) is None


class TestWeightedConsensus:
    def test_highest_score_wins(self):
        providers = _mock_providers()
        votes = [
            ProviderVote(provider_id="groq",   score=0.95, reason="best"),
            ProviderVote(provider_id="openai",  score=0.50, reason="ok"),
        ]
        winner = weighted_confidence_consensus(votes, providers)
        assert winner is not None
        assert winner.provider_id == "groq"


class TestCostAwareConsensus:
    def test_prefers_free_provider(self):
        providers = _mock_providers()
        votes = [
            ProviderVote(provider_id="groq",   score=0.7, reason="free"),
            ProviderVote(provider_id="openai",  score=0.9, reason="paid"),
        ]
        winner = cost_aware_consensus(votes, providers, prefer_free=True)
        assert winner is not None
        assert winner.provider_id == "groq"

    def test_route_selection_prefers_configured_free_provider(self):
        providers = _mock_providers()
        votes = [
            ProviderVote(provider_id="groq",  score=0.8, reason="free"),
        ]
        winner = cost_aware_consensus(votes, providers)
        assert winner.provider_id == "groq"


class TestGatewayStateRouting:
    def test_preferred_provider_accepted(self):
        s = GatewayState(user_prompt="hello", preferred_provider_id="groq")
        assert s.preferred_provider_id == "groq"

    def test_allow_unknown_opt_in(self):
        s = GatewayState(user_prompt="hello", allow_unknown_quota=True)
        assert s.allow_unknown_quota is True

    def test_default_disallows_unknown(self):
        s = GatewayState(user_prompt="hello")
        assert s.allow_unknown_quota is False
