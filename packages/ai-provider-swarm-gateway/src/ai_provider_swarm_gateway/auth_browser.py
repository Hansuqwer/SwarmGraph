"""Opt-in browser session token extraction helpers.

This module never runs automatically. Callers must explicitly choose a provider
and browser profile scope, and should store returned tokens only in the
encrypted vault.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


class BrowserAuthError(RuntimeError):
    """Raised when browser cookie extraction cannot be performed safely."""


@dataclass(frozen=True)
class BrowserSessionToken:
    provider: str
    account_id: str
    token: str
    source_browser: str
    cookie_name: str


class CookieJarProvider(Protocol):
    def load(self, browser: str) -> Iterable[object]: ...


class BrowserCookie3Provider:
    """Load cookies via optional browser-cookie3 dependency."""

    def load(self, browser: str) -> Iterable[object]:
        try:
            import browser_cookie3  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional extra
            raise BrowserAuthError("browser auth requires browser-cookie3") from exc

        loaders = {
            "chrome": getattr(browser_cookie3, "chrome", None),
            "chromium": getattr(browser_cookie3, "chromium", None),
            "firefox": getattr(browser_cookie3, "firefox", None),
            "safari": getattr(browser_cookie3, "safari", None),
            "edge": getattr(browser_cookie3, "edge", None),
        }
        loader = loaders.get(browser)
        if loader is None:
            raise BrowserAuthError(f"unsupported browser: {browser}")
        try:
            return loader()
        except Exception as exc:
            raise BrowserAuthError(f"could not read {browser} cookies") from exc


_PROVIDER_COOKIE_RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "chatgpt": ("openai", ("__Secure-next-auth.session-token", "oai-did")),
    "qwen": ("qwen", ("token", "_uab_collina")),
    "kimi": ("kimi", ("kimi-auth", "refresh_token", "access_token")),
}


def _cookie_attr(cookie: object, name: str) -> str:
    value = getattr(cookie, name, "")
    return str(value or "")


def extract_browser_session_token(
    provider: str,
    *,
    browser: str = "chrome",
    account_id: str = "browser_auto",
    cookie_provider: CookieJarProvider | None = None,
) -> BrowserSessionToken | None:
    """Return a provider-scoped browser session token, or None when absent."""
    provider_key = provider.lower().strip()
    if provider_key not in _PROVIDER_COOKIE_RULES:
        raise BrowserAuthError(f"unsupported provider: {provider}")
    browser_key = browser.lower().strip()
    canonical_provider, cookie_names = _PROVIDER_COOKIE_RULES[provider_key]
    jar_provider = cookie_provider or BrowserCookie3Provider()

    for cookie in jar_provider.load(browser_key):
        cookie_name = _cookie_attr(cookie, "name")
        cookie_value = _cookie_attr(cookie, "value")
        if cookie_name not in cookie_names or not cookie_value:
            continue
        return BrowserSessionToken(
            provider=canonical_provider,
            account_id=account_id,
            token=cookie_value,
            source_browser=browser_key,
            cookie_name=cookie_name,
        )
    return None


__all__ = [
    "BrowserAuthError",
    "BrowserCookie3Provider",
    "BrowserSessionToken",
    "extract_browser_session_token",
]
