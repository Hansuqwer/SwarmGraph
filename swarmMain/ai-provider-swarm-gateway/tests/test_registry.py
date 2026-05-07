"""Tests for provider registry loading and validation."""
from __future__ import annotations
import pytest
from src.ai_provider_swarm_gateway.registry.loader import (
    load_provider_registry, get_free_api_providers, get_provider_by_id
)


def test_provider_registry_loads():
    providers = load_provider_registry()
    assert len(providers) >= 10, "Registry should have at least 10 providers"


def test_all_providers_have_required_fields():
    providers = load_provider_registry()
    for p in providers:
        assert p.provider_id, f"provider_id empty: {p}"
        assert p.provider_name, f"provider_name empty: {p.provider_id}"
        assert p.website_url, f"website_url empty: {p.provider_id}"


def test_free_api_providers_are_correctly_flagged():
    providers = get_free_api_providers()
    for p in providers:
        assert p.is_api_free(), f"{p.provider_id} returned by get_free_api_providers but is_api_free() is False"


def test_known_free_providers_in_registry():
    """Groq, Gemini, Mistral, Cerebras should all be present and free."""
    free = {p.provider_id: p for p in get_free_api_providers()}
    expected_free = ["groq", "google_gemini", "mistral", "cerebras"]
    for pid in expected_free:
        assert pid in free, f"{pid} should be in free providers"


def test_openai_not_in_free_providers():
    free_ids = [p.provider_id for p in get_free_api_providers()]
    assert "openai" not in free_ids, "OpenAI has no free API tier — should not appear as free"


def test_anthropic_not_in_free_providers():
    free_ids = [p.provider_id for p in get_free_api_providers()]
    assert "anthropic" not in free_ids, "Anthropic has no permanent free API tier"


def test_together_ai_not_in_free_providers():
    free_ids = [p.provider_id for p in get_free_api_providers()]
    assert "together_ai" not in free_ids, "Together AI has no free tier"


def test_get_provider_by_id():
    p = get_provider_by_id("groq")
    assert p is not None
    assert p.provider_id == "groq"


def test_unknown_provider_returns_none():
    p = get_provider_by_id("nonexistent_provider_xyz")
    assert p is None


def test_dashboard_registry_shape():
    """Verify every provider has the fields the dashboard expects."""
    providers = load_provider_registry()
    for p in providers:
        assert hasattr(p.quota, "confidence")
        assert hasattr(p.quota, "api_access_available")
        assert hasattr(p.quota, "web_only_free_access")
        assert hasattr(p, "signup_url")
        assert hasattr(p, "api_docs_url")


def test_unknown_limits_have_confidence_unknown():
    """Providers with unverified limits must use confidence=unknown."""
    providers = load_provider_registry()
    for p in providers:
        if p.quota.confidence == "unknown":
            # Should not have specific request numbers claimed as facts
            daily = p.quota.free_daily_usage or ""
            assert not (daily.replace(",", "").split()[0].isdigit() if daily else False), \
                f"{p.provider_id}: has numeric free_daily_usage but confidence=unknown"


def test_project_review_exists():
    from pathlib import Path
    review_path = Path(__file__).parent.parent / "PROJECT_REVIEW.md"
    assert review_path.exists(), "PROJECT_REVIEW.md must exist"
