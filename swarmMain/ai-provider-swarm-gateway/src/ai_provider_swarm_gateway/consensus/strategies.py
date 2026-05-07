"""
AGENTS 24, 25 — Swarm Routing Specialist, Consensus Specialist
4 consensus strategies for provider selection. Policy guard applied to all.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from ..models.provider import ProviderInfo
from ..policy.guardrails import validate_provider_policy


@dataclass
class ProviderVote:
    provider_id: str
    score:       float   # 0.0–1.0
    reason:      str
    policy_ok:   bool = True


def _apply_policy_guard(
    votes: list[ProviderVote],
    providers: dict[str, ProviderInfo],
) -> list[ProviderVote]:
    """Remove any vote for a provider that fails policy checks. BFT-style safety."""
    safe: list[ProviderVote] = []
    for v in votes:
        provider = providers.get(v.provider_id)
        if provider is None:
            continue
        warnings = validate_provider_policy(provider)
        if any("WEB-ONLY" in w or "VIOLATION" in w for w in warnings):
            v.policy_ok = False
            continue
        safe.append(v)
    return safe


def majority_consensus(
    votes: list[ProviderVote],
    providers: dict[str, ProviderInfo],
) -> ProviderVote | None:
    """Simple majority — most votes wins. Policy guard applied."""
    safe = _apply_policy_guard(votes, providers)
    if not safe:
        return None
    counter: Counter[str] = Counter(v.provider_id for v in safe)
    best_id, _ = counter.most_common(1)[0]
    return next(v for v in safe if v.provider_id == best_id)


def weighted_confidence_consensus(
    votes: list[ProviderVote],
    providers: dict[str, ProviderInfo],
) -> ProviderVote | None:
    """Weighted by score — highest total confidence wins. Policy guard applied."""
    safe = _apply_policy_guard(votes, providers)
    if not safe:
        return None
    from collections import defaultdict
    weighted: dict[str, float] = defaultdict(float)
    for v in safe:
        weighted[v.provider_id] += v.score
    best_id = max(weighted, key=lambda k: weighted[k])
    return next(v for v in safe if v.provider_id == best_id)


def policy_guarded_consensus(
    votes: list[ProviderVote],
    providers: dict[str, ProviderInfo],
) -> ProviderVote | None:
    """
    BFT-style: requires 2/3 of votes to agree on a provider AND pass policy.
    Falls back to weighted_confidence if quorum not reached.
    """
    safe = _apply_policy_guard(votes, providers)
    if not safe:
        return None
    counter: Counter[str] = Counter(v.provider_id for v in safe)
    threshold = max(1, int(len(safe) * 0.67))
    for pid, count in counter.most_common():
        if count >= threshold:
            return next(v for v in safe if v.provider_id == pid)
    return weighted_confidence_consensus(votes, providers)


def cost_aware_consensus(
    votes: list[ProviderVote],
    providers: dict[str, ProviderInfo],
    prefer_free: bool = True,
) -> ProviderVote | None:
    """
    Prefers providers with confirmed free API tier.
    Among free providers: highest confidence score wins.
    Among paid providers: falls back to weighted_confidence.
    Policy guard applied.
    """
    safe = _apply_policy_guard(votes, providers)
    if not safe:
        return None

    free_votes = [v for v in safe if providers.get(v.provider_id) and
                  providers[v.provider_id].is_api_free()]
    if prefer_free and free_votes:
        return max(free_votes, key=lambda v: v.score)
    return weighted_confidence_consensus(safe, providers)
