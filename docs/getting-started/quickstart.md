# Quickstart

```bash
uv run ai-provider-gateway --help
uv run ai-provider-gateway swarm --prompt "implement add(a,b)" --anti-drift off --max-agents 3 --json
```

For live 9router execution:

```bash
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<your-key> \
uv run ai-provider-gateway swarm \
  --prompt "implement add(a,b)" \
  --backend gateway --provider 9router --model kc/kilo-auto/free \
  --anti-drift off --max-agents 3 --json
```
