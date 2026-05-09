import pytest
from ai_provider_swarm_gateway.quota.pool import SecretStore, VaultError, create_vault_key


def test_create_key_file_mode(tmp_path):
    key_path = tmp_path / "vault.key"

    key = create_vault_key(key_path)

    assert key_path.read_text(encoding="utf-8") == key
    assert oct(key_path.stat().st_mode & 0o777) == "0o600"


def test_vault_encrypts_and_roundtrips(tmp_path):
    key_path = tmp_path / "vault.key"
    create_vault_key(key_path)
    vault_path = tmp_path / "secrets.json.enc"

    store = SecretStore(vault_path, key_path=key_path)
    store.add_key("openai", "acct1", "secret-value")

    assert b"secret-value" not in vault_path.read_bytes()
    assert oct(vault_path.stat().st_mode & 0o777) == "0o600"
    loaded = SecretStore(vault_path, key_path=key_path)
    assert loaded.get_key_for_account("openai", "acct1") == "secret-value"


def test_vault_upsert(tmp_path):
    key_path = tmp_path / "vault.key"
    create_vault_key(key_path)
    store = SecretStore(tmp_path / "secrets.json.enc", key_path=key_path)

    store.add_key("openai", "acct1", "old")
    store.add_key("openai", "acct1", "new")

    assert store.get_account_ids("openai") == ["acct1"]
    assert store.get_key_for_account("openai", "acct1") == "new"


def test_vault_corrupt_file_fails_closed(tmp_path):
    key_path = tmp_path / "vault.key"
    create_vault_key(key_path)
    vault_path = tmp_path / "secrets.json.enc"
    vault_path.write_bytes(b"not encrypted")

    with pytest.raises(VaultError):
        SecretStore(vault_path, key_path=key_path)


def test_vault_missing_key_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER_GATEWAY_VAULT_KEY", raising=False)

    with pytest.raises(VaultError):
        SecretStore(tmp_path / "secrets.json.enc", key_path=tmp_path / "missing.key")


def test_vault_can_use_env_key(tmp_path, monkeypatch):
    key = create_vault_key(tmp_path / "vault.key")
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_VAULT_KEY", key)

    store = SecretStore(tmp_path / "secrets.json.enc", key_path=None)
    store.add_key("grok", "acct", "x")

    assert store.to_summary() == {"grok": ["acct"]}
