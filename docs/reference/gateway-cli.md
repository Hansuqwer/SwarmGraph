# Gateway CLI

`ai-provider-gateway` and `swarmgraph` are equivalent console entry points.

```bash
uv run ai-provider-gateway --help
uv run swarmgraph --help
uv run ai-provider-gateway providers list
uv run ai-provider-gateway route --prompt "pong"
uv run ai-provider-gateway quota show --json
uv run ai-provider-gateway audit verify audit.jsonl
```

Use `swarmgraph` when you want the project-branded alias; use `ai-provider-gateway` when you want the package-specific command name.
