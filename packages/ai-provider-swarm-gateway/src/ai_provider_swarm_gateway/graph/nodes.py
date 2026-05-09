"""
AGENTS 16-23 — LangGraph node implementations.
Each node is a pure function: dict -> dict (GatewayState serialized).
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import Any

from ..consensus.strategies import (
    ProviderVote,
    cost_aware_consensus,
    policy_guarded_consensus,
    weighted_confidence_consensus,
)
from ..models.state import GatewayResponse, GatewayState, ProviderAttempt, RoutingDecision
from ..policy.guardrails import (
    can_route_to_provider,
    reject_quota_evasion,
    validate_provider_policy,
)
from ..providers.base import ProviderAdapter
from ..providers.mock_adapter import MockAdapter
from ..quota.tracker import QuotaTracker
from ..registry.loader import load_provider_registry

# ── Shared resources (initialized once per import) ───────────────────────────

_registry = None
_registry_dict = None
_quota_tracker = QuotaTracker()


def _get_registry():
    global _registry, _registry_dict
    if _registry is None:
        _registry = load_provider_registry()
        _registry_dict = {p.provider_id: p for p in _registry}
    return _registry, _registry_dict


def _get_adapter(provider_id: str) -> ProviderAdapter:
    """Return the correct adapter for a provider_id. Falls back to mock."""
    from ..providers.anthropic_adapter import AnthropicAdapter
    from ..providers.deepseek_adapter import DeepSeekAdapter
    from ..providers.glm_adapter import GLMAdapter
    from ..providers.google_adapter import GoogleAdapter
    from ..providers.grok_adapter import GrokAdapter
    from ..providers.groq_adapter import GroqAdapter
    from ..providers.kimi_adapter import KimiAdapter
    from ..providers.nine_router_adapter import NineRouterAdapter
    from ..providers.openai_adapter import OpenAIAdapter
    from ..providers.openrouter_adapter import OpenRouterAdapter
    from ..providers.qwen_adapter import QwenAdapter

    adapters: dict[str, ProviderAdapter] = {
        "openai": OpenAIAdapter(),
        "anthropic": AnthropicAdapter(),
        "google_gemini": GoogleAdapter(),
        "groq": GroqAdapter(),
        "grok": GrokAdapter(),
        "deepseek": DeepSeekAdapter(),
        "qwen": QwenAdapter(),
        "zhipu_glm": GLMAdapter(),
        "moonshot_kimi": KimiAdapter(),
        "openrouter": OpenRouterAdapter(),
        "9router": NineRouterAdapter(),
        "mock": MockAdapter(),
    }
    return adapters.get(provider_id, MockAdapter())


# ── Node 1: Intake ────────────────────────────────────────────────────────────


def intake_node(state: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize incoming request."""
    s = GatewayState.from_json_dict(state)
    s.log("intake_node: validating request")

    # Check for quota evasion flags in metadata
    violations = reject_quota_evasion({"prompt_length": len(s.user_prompt)})
    for v in violations:
        s.add_policy_violation(v)

    if not s.user_prompt.strip():
        s.add_error("user_prompt is empty")
        s.is_safe_to_proceed = False

    s.log(f"intake_node: prompt accepted (len={len(s.user_prompt)})")
    return s.to_json_dict()


# ── Node 2: Classify Request ──────────────────────────────────────────────────


def classify_request_node(state: dict[str, Any]) -> dict[str, Any]:
    """Infer requested capability from prompt if not specified."""
    s = GatewayState.from_json_dict(state)
    if not s.is_safe_to_proceed:
        return s.to_json_dict()

    if s.requested_capability is None:
        prompt_lower = s.user_prompt.lower()
        if any(w in prompt_lower for w in ["image", "picture", "draw", "generate image"]):
            s.requested_capability = "image"
        elif any(w in prompt_lower for w in ["embed", "embedding", "vector"]):
            s.requested_capability = "embeddings"
        elif any(w in prompt_lower for w in ["code", "function", "debug", "refactor"]):
            s.requested_capability = "code"
        else:
            s.requested_capability = "chat"

    s.log(f"classify_request_node: capability={s.requested_capability}")
    return s.to_json_dict()


# ── Node 3: Provider Filter ───────────────────────────────────────────────────


def provider_filter_node(state: dict[str, Any]) -> dict[str, Any]:
    """Filter providers by capability, credentials, policy, and free-tier status."""
    s = GatewayState.from_json_dict(state)
    if not s.is_safe_to_proceed:
        return s.to_json_dict()

    _, registry_dict = _get_registry()
    candidates: list[str] = []
    rejected: list[str] = []

    for provider_id, provider in registry_dict.items():
        # Capability check
        cap = s.requested_capability or "chat"
        if cap not in (provider.capabilities or []) and cap != "chat":
            rejected.append(provider_id)
            continue

        # Local providers (Ollama, LM Studio) — always available if configured
        adapter = _get_adapter(provider_id)
        cred_available = provider.is_local or adapter.is_configured()

        # Policy check
        can_route, reasons = can_route_to_provider(
            provider=provider,
            credential_available=cred_available,
            usage=_quota_tracker.get_usage(provider_id),
            allow_unknown_quota=s.allow_unknown_quota,
        )

        if can_route:
            candidates.append(provider_id)
        else:
            rejected.append(provider_id)
            for r in reasons:
                s.log(f"filter_rejected [{provider_id}]: {r}")

    # Prefer configured providers
    s.candidate_providers = candidates
    s.log(f"provider_filter_node: {len(candidates)} candidates, {len(rejected)} rejected")
    return s.to_json_dict()


# ── Node 4: Quota Check ───────────────────────────────────────────────────────


def quota_check_node(state: dict[str, Any]) -> dict[str, Any]:
    """Remove providers with exhausted known quotas."""
    s = GatewayState.from_json_dict(state)
    if not s.is_safe_to_proceed:
        return s.to_json_dict()

    _, registry_dict = _get_registry()
    still_available: list[str] = []
    for pid in s.candidate_providers:
        provider = registry_dict.get(pid)
        if provider is None:
            continue
        usage = _quota_tracker.get_usage(pid)
        # If we know the daily limit, check it
        daily_str = provider.quota.free_daily_usage or ""
        max_req = None
        if "req/day" in daily_str:
            try:
                max_req = int(daily_str.split()[0].replace(",", ""))
            except ValueError:
                pass
        if max_req and _quota_tracker.is_exhausted(pid, max_req):
            s.log(f"quota_check_node: [{pid}] quota exhausted ({usage.used_requests}/{max_req})")
            continue
        still_available.append(pid)

    s.candidate_providers = still_available
    s.log(f"quota_check_node: {len(still_available)} providers pass quota check")
    return s.to_json_dict()


# ── Node 5: Swarm Route ───────────────────────────────────────────────────────


def swarm_route_node(state: dict[str, Any]) -> dict[str, Any]:
    """Parallel evaluation of candidate providers → ProviderVote list."""
    s = GatewayState.from_json_dict(state)
    if not s.is_safe_to_proceed or not s.candidate_providers:
        s.log("swarm_route_node: no candidates to evaluate")
        return s.to_json_dict()

    _, registry_dict = _get_registry()
    votes: list[dict[str, Any]] = []

    for pid in s.candidate_providers:
        provider = registry_dict.get(pid)
        if not provider:
            continue
        score = 0.5
        reason_parts: list[str] = []

        # Prefer confirmed free API tier
        if provider.is_api_free():
            score += 0.3
            reason_parts.append("confirmed_free_api")

        # Prefer local (no cost, no rate limit)
        if provider.is_local:
            score += 0.2
            reason_parts.append("local_provider")

        # Prefer verified confidence
        if provider.quota.confidence == "verified":
            score += 0.1
            reason_parts.append("verified_data")
        elif provider.quota.confidence == "partially_verified":
            score += 0.05

        # Prefer user's preferred provider
        if s.preferred_provider_id and pid == s.preferred_provider_id:
            score += 0.5
            reason_parts.append("user_preferred")

        # Check health (simplified — no real health check in stub)
        score = min(1.0, score)
        votes.append(
            {"provider_id": pid, "score": score, "reason": ", ".join(reason_parts) or "default"}
        )

    # Store votes in state via audit log (votes will be read by consensus_node)
    import json

    s.log(f"swarm_route_node: votes={json.dumps(votes)}")
    s.audit_log = s.audit_log + ["__votes__:" + json.dumps(votes)]
    return s.to_json_dict()


# ── Node 6: Consensus ─────────────────────────────────────────────────────────


def consensus_node(state: dict[str, Any]) -> dict[str, Any]:
    """Apply cost-aware + policy-guarded consensus to select best provider."""
    s = GatewayState.from_json_dict(state)
    if not s.is_safe_to_proceed:
        return s.to_json_dict()

    _, registry_dict = _get_registry()

    # Recover votes from audit log
    import json

    votes: list[ProviderVote] = []
    for entry in s.audit_log:
        if entry.startswith("__votes__:"):
            raw_votes = json.loads(entry[len("__votes__:") :])
            votes = [ProviderVote(**v) for v in raw_votes]
            break

    if not votes:
        s.log("consensus_node: no votes found, cannot select provider")
        s.routing_decision = RoutingDecision(
            selected_provider_id=None,
            selected_model=None,
            reason="No candidate providers passed all filters",
            rejected_provider_ids=[],
            requires_user_action=True,
        )
        return s.to_json_dict()

    # Run cost-aware consensus (prefers free providers)
    winner = cost_aware_consensus(votes, registry_dict, prefer_free=True)
    if not winner:
        winner = weighted_confidence_consensus(votes, registry_dict)

    rejected = [
        v.provider_id
        for v in votes
        if not v.policy_ok or v.provider_id != (winner.provider_id if winner else "")
    ]
    policy_warnings = []
    if winner:
        policy_warnings = (
            validate_provider_policy(registry_dict[winner.provider_id])
            if winner.provider_id in registry_dict
            else []
        )

    s.routing_decision = RoutingDecision(
        selected_provider_id=winner.provider_id if winner else None,
        selected_model=registry_dict[winner.provider_id].supported_models[0]
        if winner
        and winner.provider_id in registry_dict
        and registry_dict[winner.provider_id].supported_models
        else None,
        reason=winner.reason if winner else "No provider passed consensus",
        rejected_provider_ids=rejected,
        policy_warnings=policy_warnings,
        requires_user_action=(winner is None),
    )
    s.log(f"consensus_node: selected={s.routing_decision.selected_provider_id}")
    return s.to_json_dict()


# ── Node 7: Provider Call ─────────────────────────────────────────────────────


def provider_call_node(state: dict[str, Any]) -> dict[str, Any]:
    """Make the actual provider API call."""
    s = GatewayState.from_json_dict(state)
    if (
        not s.is_safe_to_proceed
        or not s.routing_decision
        or not s.routing_decision.selected_provider_id
    ):
        s.log("provider_call_node: skipped — no provider selected")
        return s.to_json_dict()

    provider_id = s.routing_decision.selected_provider_id
    model_id = s.routing_decision.selected_model
    adapter = _get_adapter(provider_id)

    attempt = ProviderAttempt(
        provider_id=provider_id,
        model_id=model_id,
        started_at=datetime.now(tz=UTC),
    )

    s.log(f"provider_call_node: calling {provider_id}")
    response = adapter.call(s.user_prompt, model=model_id)

    attempt.success = response.error is None
    attempt.error = response.error
    attempt.finished_at = datetime.now(tz=UTC)
    attempt.tokens_used = response.tokens_used

    s.attempts = s.attempts + [attempt]
    s.provider_response = response
    s.log(f"provider_call_node: success={attempt.success}")
    return s.to_json_dict()


# ── Node 8: Response Validation ───────────────────────────────────────────────


def response_validation_node(state: dict[str, Any]) -> dict[str, Any]:
    """Validate response quality, detect errors, prepare for usage update."""
    s = GatewayState.from_json_dict(state)
    if not s.provider_response:
        s.add_error("No provider response received")
        return s.to_json_dict()

    if s.provider_response.error:
        s.add_error(f"Provider error: {s.provider_response.error}")

    if s.provider_response.content and len(s.provider_response.content.strip()) < 2:
        s.add_error("Provider returned empty content")

    s.log(f"response_validation_node: validated response from {s.provider_response.provider_id}")
    return s.to_json_dict()


# ── Node 9: Usage Update ──────────────────────────────────────────────────────


def usage_update_node(state: dict[str, Any]) -> dict[str, Any]:
    """Update local quota tracker. Append-only. Write audit log entry."""
    s = GatewayState.from_json_dict(state)
    if not s.provider_response:
        return s.to_json_dict()

    pid = s.provider_response.provider_id
    tokens = s.provider_response.tokens_used or 0
    success = s.provider_response.error is None

    if success:
        _quota_tracker.increment(pid, requests=1, tokens=tokens)
        s.log(f"usage_update_node: incremented usage for {pid} (+1 req, +{tokens} tokens)")
    else:
        s.log(f"usage_update_node: skipped increment (failed call to {pid})")

    return s.to_json_dict()
