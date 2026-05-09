# Vault Backup And Restore

Back up both files together:

```bash
mkdir -p ~/swarmgraph-backup
cp -p ~/.ai_provider_gateway/vault.key ~/swarmgraph-backup/vault.key
cp -p ~/.ai_provider_gateway/secrets.json.enc ~/swarmgraph-backup/secrets.json.enc
chmod 600 ~/swarmgraph-backup/vault.key ~/swarmgraph-backup/secrets.json.enc
```

The encrypted vault is useless without the Fernet key. Never commit either file.

Restore:

```bash
mkdir -p ~/.ai_provider_gateway
cp -p ~/swarmgraph-backup/vault.key ~/.ai_provider_gateway/vault.key
cp -p ~/swarmgraph-backup/secrets.json.enc ~/.ai_provider_gateway/secrets.json.enc
chmod 600 ~/.ai_provider_gateway/vault.key ~/.ai_provider_gateway/secrets.json.enc
uv run ai-provider-gateway tenants pool list
```

`tenants pool sync --pull` also verifies downloaded encrypted vaults before
replacement when the local key is available.
