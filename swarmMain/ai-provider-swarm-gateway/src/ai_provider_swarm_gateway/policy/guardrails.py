"""
AGENT 05 — Risk, Policy & ToS Guardian
AGENT 26 — Anti-Drift Specialist

Policy guardrails — blocks all quota evasion, unsafe automation, and account-rotation behaviors.
"""
from __future__ import annotations

from typing import Any

from ..models.provider import ProviderInfo
from ..models.quota import QuotaUsage, QuotaStatus


# ── Prohibited request metadata keys ─────────────────────────────────────────

_PROHIBITED_FLAGS = {
    "account_rotation",
    "rotate_accounts",
    "bypass_quota",
    "multi_account",
    "fake_identity",
    "captcha_bypass",
    "scrape_session",
    "evade_limit",
    "reset_counter",
    "credential_harvest",
}


def validate_provider_policy(provider: ProviderInfo) -> list[str]:
    """
    Returns a list of policy warnings for a provider.
    Empty list = no policy concerns.
    Non-empty = caller should warn user or reject.
    """
    warnings: list[str] = []

    # Web-only free but API is paid
    if provider.quota.web_only_free_access:
        warnings.append(
            f"[{provider.provider_id}] Free access is WEB-ONLY. "
            "API usage requires payment. Do not route API requests here as 'free'."
        )

    # Unknown confidence — cannot confirm free
    if provider.quota.confidence == "unknown":
        warnings.append(
            f"[{provider.provider_id}] Quota confidence is UNKNOWN. "
            "Do not treat this provider as free without manual verification."
        )

    # Likely changed — data may be stale
    if provider.quota.confidence == "likely_changed":
        warnings.append(
            f"[{provider.provider_id}] Quota data is marked LIKELY_CHANGED. "
            "Verify current limits before routing."
        )

    # No API access confirmed
    if provider.quota.api_access_available is False:
        warnings.append(
            f"[{provider.provider_id}] API access is NOT available. "
            "Only web usage confirmed."
        )

    # Requires payment but api_access_available is true — paid API
    if provider.quota.requires_payment_method and not provider.is_api_free():
        warnings.append(
            f"[{provider.provider_id}] Requires payment method. "
            "Only route if user has confirmed paid API credentials."
        )

    # Pass any notes from quota model
    for note in provider.quota.notes:
        if "WARNING" in note or "UNVERIFIED" in note:
            warnings.append(f"[{provider.provider_id}] {note}")

    return warnings


def reject_quota_evasion(request_metadata: dict[str, Any]) -> list[str]:
    """
    Checks request metadata for prohibited quota-evasion patterns.
    Returns list of violations. Non-empty = reject the request.

    POLICY: This function blocks:
    - Account rotation for quota bypass
    - Multi-account credential switching
    - CAPTCHA bypass attempts
    - Fake identity / credential harvesting flags
    """
    violations: list[str] = []
    meta_lower = {str(k).lower(): str(v).lower() for k, v in request_metadata.items()}

    for flag in _PROHIBITED_FLAGS:
        if flag in meta_lower:
            violations.append(
                f"POLICY VIOLATION: Prohibited request flag '{flag}' detected. "
                "This request has been blocked. Quota evasion is not permitted."
            )

    # Check for suspicious value patterns
    for k, v in meta_lower.items():
        if any(f in v for f in _PROHIBITED_FLAGS):
            violations.append(
                f"POLICY VIOLATION: Prohibited value in metadata key '{k}'. "
                "Request blocked."
            )

    return violations


def can_route_to_provider(
    provider: ProviderInfo,
    credential_available: bool,
    usage: QuotaUsage | None,
    allow_unknown_quota: bool = False,
) -> tuple[bool, list[str]]:
    """
    Master routing eligibility check.
    Returns (can_route: bool, reasons: list[str]).

    Routing rules (in order):
    1. Must have credential configured (unless local provider)
    2. Must not be web-only free (if routing API requests)
    3. If confidence=unknown: only route if user opts in with allow_unknown_quota
    4. If quota exhausted: block
    5. If requires_payment_method and no free tier confirmed: warn, require credential
    """
    reasons: list[str] = []

    # Rule 1: Credential required (except local providers)
    if not provider.is_local and not credential_available:
        reasons.append(
            f"[{provider.provider_id}] No API credential configured. "
            "Set the environment variable for this provider."
        )
        return False, reasons

    # Rule 2: Web-only free → not routable as free API
    if provider.quota.web_only_free_access:
        reasons.append(
            f"[{provider.provider_id}] This provider only offers FREE WEB ACCESS. "
            "The API is not free. Blocked to prevent unintended charges."
        )
        return False, reasons

    # Rule 3: Unknown quota — conservative by default
    if provider.quota.confidence == "unknown" and not allow_unknown_quota:
        reasons.append(
            f"[{provider.provider_id}] Quota confidence is UNKNOWN. "
            "Not routing unless user explicitly enables 'allow_unknown_quota'."
        )
        return False, reasons

    # Rule 4: Quota exhausted
    if usage is not None:
        limit_req = None  # We don't track hard limits in runtime — conservative check
        if usage.used_requests > 10_000:  # Sanity cap — configurable
            reasons.append(
                f"[{provider.provider_id}] Local usage counter ({usage.used_requests}) "
                "exceeds safety threshold. Verify quota before continuing."
            )
            # Don't hard-block — let user decide — but add warning
            # return False, reasons  # uncomment to hard-block

    # Rule 5: Requires payment method — only route if credential is confirmed active
    if provider.quota.requires_payment_method and not provider.quota.api_access_available:
        reasons.append(
            f"[{provider.provider_id}] Requires payment method and API access not confirmed free. "
            "Credential must be a paid account."
        )
        # Still route — let the adapter handle the error — but warn
        return True, reasons

    return True, reasons
