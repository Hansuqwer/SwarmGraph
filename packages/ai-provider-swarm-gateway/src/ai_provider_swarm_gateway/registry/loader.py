"""
Registry loader — reads providers.yaml and validates all entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..models.provider import ProviderInfo


_REGISTRY_PATH = Path(__file__).parent / "providers.yaml"


def load_provider_registry(path: Path | None = None) -> list[ProviderInfo]:
    """Load and validate all providers from YAML. Returns list of validated ProviderInfo."""
    registry_path = path or _REGISTRY_PATH
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    providers_raw: list[dict[str, Any]] = raw.get("providers", [])
    providers: list[ProviderInfo] = []
    errors: list[str] = []
    for entry in providers_raw:
        try:
            # Flatten quota sub-dict
            quota_raw = {
                "free_daily_usage": entry.pop("free_daily_usage", None),
                "free_monthly_usage": entry.pop("free_monthly_usage", None),
                "trial_credits": entry.pop("trial_credits", None),
                "requires_payment_method": entry.pop("requires_payment_method", None),
                "api_access_available": entry.pop("api_access_available", None),
                "web_only_free_access": entry.pop("web_only_free_access", None),
                "rate_limits": entry.pop("rate_limits", None),
                "quota_reset_policy": entry.pop("quota_reset_policy", None),
                "confidence": entry.pop("confidence", "unknown"),
            }
            entry["quota"] = quota_raw
            providers.append(ProviderInfo.model_validate(entry))
        except (ValidationError, Exception) as e:
            errors.append(f"Provider '{entry.get('provider_id', 'UNKNOWN')}': {e}")
    if errors:
        import warnings

        for err in errors:
            warnings.warn(f"Registry load error: {err}", stacklevel=2)
    return providers


def get_provider_by_id(provider_id: str, path: Path | None = None) -> ProviderInfo | None:
    for p in load_provider_registry(path):
        if p.provider_id == provider_id:
            return p
    return None


def get_free_api_providers(path: Path | None = None) -> list[ProviderInfo]:
    """Return only providers with confirmed free API access."""
    return [p for p in load_provider_registry(path) if p.is_api_free()]
