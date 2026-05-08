from dataclasses import dataclass

from typer.testing import CliRunner

from ai_provider_swarm_gateway.auth_browser import (
    BrowserAuthError,
    extract_browser_session_token,
)
from ai_provider_swarm_gateway.cli import app
from ai_provider_swarm_gateway.quota.pool import SecretStore, create_vault_key


runner = CliRunner()


@dataclass
class _Cookie:
    name: str
    value: str


class _Provider:
    def __init__(self, cookies):
        self.cookies = cookies
        self.browser = None

    def load(self, browser):
        self.browser = browser
        return self.cookies


def test_extract_browser_session_token_provider_scoped():
    provider = _Provider([_Cookie("__Secure-next-auth.session-token", "secret")])

    token = extract_browser_session_token("chatgpt", browser="chrome", cookie_provider=provider)

    assert token is not None
    assert token.provider == "openai"
    assert token.token == "secret"
    assert token.source_browser == "chrome"


def test_extract_browser_session_token_missing_returns_none():
    provider = _Provider([_Cookie("unrelated", "secret")])

    assert extract_browser_session_token("chatgpt", cookie_provider=provider) is None


def test_extract_browser_session_token_rejects_unknown_provider():
    try:
        extract_browser_session_token("unknown", cookie_provider=_Provider([]))
    except BrowserAuthError as exc:
        assert "unsupported provider" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected BrowserAuthError")


def test_auth_import_browser_dry_run_never_prints_token(monkeypatch):
    from ai_provider_swarm_gateway.auth_browser import BrowserSessionToken
    import ai_provider_swarm_gateway.auth_browser as auth_mod

    def fake_extract(*args, **kwargs):
        return BrowserSessionToken("openai", "acct", "secret-token", "chrome", "cookie")

    monkeypatch.setattr(auth_mod, "extract_browser_session_token", fake_extract)

    result = runner.invoke(app, ["auth", "import-browser", "chatgpt", "--dry-run"])

    assert result.exit_code == 0
    assert "secret-token" not in result.stdout
    assert "found openai token" in result.stdout


def test_auth_import_browser_stores_in_vault(monkeypatch, tmp_path):
    from ai_provider_swarm_gateway.auth_browser import BrowserSessionToken
    import ai_provider_swarm_gateway.auth_browser as auth_mod

    key_path = tmp_path / "vault.key"
    create_vault_key(key_path)
    vault_path = tmp_path / "secrets.json.enc"

    def fake_extract(*args, **kwargs):
        return BrowserSessionToken("openai", "acct", "secret-token", "chrome", "cookie")

    monkeypatch.setattr(auth_mod, "extract_browser_session_token", fake_extract)

    result = runner.invoke(
        app,
        [
            "auth",
            "import-browser",
            "chatgpt",
            "--vault-path",
            str(vault_path),
            "--key-path",
            str(key_path),
        ],
    )

    assert result.exit_code == 0
    assert "secret-token" not in result.stdout
    loaded = SecretStore(vault_path, key_path=key_path)
    assert loaded.get_key_for_account("openai", "acct") == "secret-token"
