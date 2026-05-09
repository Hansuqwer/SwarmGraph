# Gateway CLI

`ai-provider-gateway` and `swarmgraph` are equivalent console entry points.

```bash
uv run ai-provider-gateway --help
uv run swarmgraph --help
uv run ai-provider-gateway providers list
uv run ai-provider-gateway route --prompt "pong"
uv run ai-provider-gateway quota show --json
uv run ai-provider-gateway audit verify audit.jsonl
uv run ai-provider-gateway mcp-toolbox tools --json
uv run ai-provider-gateway mcp-toolbox config
```

Use `swarmgraph` when you want the project-branded alias; use
`ai-provider-gateway` when you want the package-specific command name.

## Optional MCP toolbox

The MCP toolbox is an optional CLI surface for AI-assisted Flutter/mobile
workflows. Install the optional SDK integration when you need to run the stdio
MCP server:

```bash
pip install 'ai-provider-swarm-gateway[mcp-toolbox]'
ai-provider-gateway mcp-toolbox serve
```

The read-only helper commands (`tools`, `doctor`, `config`) are safe to run
without live provider credentials. The `serve` command imports the MCP SDK only
when explicitly invoked.
