import json

from ai_provider_swarm_gateway.cli import app
from ai_provider_swarm_gateway.quota.pool import SecretStore, create_vault_key
from typer.testing import CliRunner

runner = CliRunner()


def test_pool_init_creates_key(tmp_path):
    key_path = tmp_path / "vault.key"

    result = runner.invoke(app, ["tenants", "pool", "init", "--key-path", str(key_path)])

    assert result.exit_code == 0
    assert key_path.exists()
    assert oct(key_path.stat().st_mode & 0o777) == "0o600"


def test_pool_add_and_list_never_print_secret(tmp_path):
    key_path = tmp_path / "vault.key"
    vault_path = tmp_path / "secrets.json.enc"
    create_vault_key(key_path)

    add = runner.invoke(
        app,
        [
            "tenants",
            "pool",
            "add",
            "openai",
            "acct1",
            "--secret",
            "secret-value",
            "--vault-path",
            str(vault_path),
            "--key-path",
            str(key_path),
        ],
    )
    assert add.exit_code == 0
    assert "secret-value" not in add.stdout

    listed = runner.invoke(
        app,
        [
            "tenants",
            "pool",
            "list",
            "--json",
            "--vault-path",
            str(vault_path),
            "--key-path",
            str(key_path),
        ],
    )
    assert listed.exit_code == 0
    assert "secret-value" not in listed.stdout
    assert json.loads(listed.stdout) == {"openai": ["acct1"]}
    loaded = SecretStore(vault_path, key_path=key_path)
    assert loaded.get_key_for_account("openai", "acct1") == "secret-value"


def test_pool_sync_requires_one_direction():
    result = runner.invoke(app, ["tenants", "pool", "sync", "--bucket", "b"])

    assert result.exit_code == 2
    assert "choose exactly one" in (result.stdout + (result.stderr or ""))


def test_pool_sync_push_uses_s3_without_printing_secret(monkeypatch, tmp_path):
    vault_path = tmp_path / "secrets.json.enc"
    vault_path.write_bytes(b"encrypted-secret-value")
    calls = {}

    class _S3:
        def upload_file(self, filename, bucket, key, Config=None):
            calls["upload"] = (filename, bucket, key, Config is not None)

    class _Boto3:
        @staticmethod
        def client(name):
            assert name == "s3"
            return _S3()

    class _TransferConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    import sys
    import types

    boto3_mod = types.ModuleType("boto3")
    boto3_mod.client = _Boto3.client
    transfer_mod = types.ModuleType("boto3.s3.transfer")
    transfer_mod.TransferConfig = _TransferConfig
    s3_mod = types.ModuleType("boto3.s3")
    s3_mod.transfer = transfer_mod
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "boto3.s3", s3_mod)
    monkeypatch.setitem(sys.modules, "boto3.s3.transfer", transfer_mod)

    result = runner.invoke(
        app,
        [
            "tenants",
            "pool",
            "sync",
            "--bucket",
            "bucket",
            "--key",
            "vault.enc",
            "--vault-path",
            str(vault_path),
            "--push",
        ],
    )

    assert result.exit_code == 0
    assert "encrypted-secret-value" not in result.stdout
    assert calls["upload"] == (str(vault_path), "bucket", "vault.enc", True)


def test_pool_sync_pull_is_atomic_and_requires_confirm_for_overwrite(monkeypatch, tmp_path):
    vault_path = tmp_path / "secrets.json.enc"
    vault_path.write_bytes(b"old-vault")
    calls = {}

    class _S3:
        def download_file(self, bucket, key, filename, Config=None):
            calls["download"] = (bucket, key, filename, Config is not None)
            assert filename.endswith(".secrets.json.enc.download")
            with open(filename, "wb") as fh:
                fh.write(b"new-vault")

    class _Boto3:
        @staticmethod
        def client(name):
            assert name == "s3"
            return _S3()

    class _TransferConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    import sys
    import types

    boto3_mod = types.ModuleType("boto3")
    boto3_mod.client = _Boto3.client
    transfer_mod = types.ModuleType("boto3.s3.transfer")
    transfer_mod.TransferConfig = _TransferConfig
    s3_mod = types.ModuleType("boto3.s3")
    s3_mod.transfer = transfer_mod
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "boto3.s3", s3_mod)
    monkeypatch.setitem(sys.modules, "boto3.s3.transfer", transfer_mod)

    denied = runner.invoke(
        app,
        [
            "tenants",
            "pool",
            "sync",
            "--bucket",
            "bucket",
            "--key",
            "vault.enc",
            "--vault-path",
            str(vault_path),
            "--pull",
        ],
        input="n\n",
    )
    assert denied.exit_code != 0
    assert vault_path.read_bytes() == b"old-vault"

    pulled = runner.invoke(
        app,
        [
            "tenants",
            "pool",
            "sync",
            "--bucket",
            "bucket",
            "--key",
            "vault.enc",
            "--vault-path",
            str(vault_path),
            "--pull",
            "--yes",
        ],
    )
    assert pulled.exit_code == 0
    assert vault_path.read_bytes() == b"new-vault"
    assert calls["download"][0:2] == ("bucket", "vault.enc")


def test_pool_sync_pull_validates_downloaded_vault_when_key_available(monkeypatch, tmp_path):
    key_path = tmp_path / "vault.key"
    create_vault_key(key_path)
    vault_path = tmp_path / "secrets.json.enc"
    old = SecretStore(vault_path, key_path=key_path)
    old.add_key("openai", "old", "old-secret")
    incoming = tmp_path / "incoming.enc"
    new = SecretStore(incoming, key_path=key_path)
    new.add_key("openai", "new", "new-secret")

    class _S3:
        def download_file(self, bucket, key, filename, Config=None):
            with open(filename, "wb") as fh:
                fh.write(incoming.read_bytes())

    class _TransferConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    import sys
    import types

    boto3_mod = types.ModuleType("boto3")
    boto3_mod.client = lambda name: _S3()
    transfer_mod = types.ModuleType("boto3.s3.transfer")
    transfer_mod.TransferConfig = _TransferConfig
    s3_mod = types.ModuleType("boto3.s3")
    s3_mod.transfer = transfer_mod
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "boto3.s3", s3_mod)
    monkeypatch.setitem(sys.modules, "boto3.s3.transfer", transfer_mod)

    result = runner.invoke(
        app,
        [
            "tenants",
            "pool",
            "sync",
            "--bucket",
            "bucket",
            "--key",
            "vault.enc",
            "--vault-path",
            str(vault_path),
            "--key-path",
            str(key_path),
            "--pull",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert SecretStore(vault_path, key_path=key_path).to_summary() == {"openai": ["new"]}


def test_pool_sync_pull_corrupt_vault_keeps_old_when_key_available(monkeypatch, tmp_path):
    key_path = tmp_path / "vault.key"
    create_vault_key(key_path)
    vault_path = tmp_path / "secrets.json.enc"
    old = SecretStore(vault_path, key_path=key_path)
    old.add_key("openai", "old", "old-secret")
    old_bytes = vault_path.read_bytes()

    class _S3:
        def download_file(self, bucket, key, filename, Config=None):
            with open(filename, "wb") as fh:
                fh.write(b"not-a-fernet-vault")

    class _TransferConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    import sys
    import types

    boto3_mod = types.ModuleType("boto3")
    boto3_mod.client = lambda name: _S3()
    transfer_mod = types.ModuleType("boto3.s3.transfer")
    transfer_mod.TransferConfig = _TransferConfig
    s3_mod = types.ModuleType("boto3.s3")
    s3_mod.transfer = transfer_mod
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "boto3.s3", s3_mod)
    monkeypatch.setitem(sys.modules, "boto3.s3.transfer", transfer_mod)

    result = runner.invoke(
        app,
        [
            "tenants",
            "pool",
            "sync",
            "--bucket",
            "bucket",
            "--key",
            "vault.enc",
            "--vault-path",
            str(vault_path),
            "--key-path",
            str(key_path),
            "--pull",
            "--yes",
        ],
    )

    assert result.exit_code == 1
    assert vault_path.read_bytes() == old_bytes
