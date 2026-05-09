# Quickstart

```bash
uv run ai-provider-gateway --help
uv run swarmgraph --help  # same CLI, shorter alias
uv run ai-provider-gateway swarm --prompt "implement add(a,b)" --anti-drift off --max-agents 3 --json
```

For live provider execution through the gateway:

```bash
uv run ai-provider-gateway swarm \
  --prompt "implement add(a,b)" \
  --backend gateway --provider <provider-id> --model <model-id> \
  --anti-drift off --max-agents 3 --json
```
