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
workflows. Install the optional Flutter extra when you need to run the stdio
MCP server or Flutter tool workflow:

```bash
pip install 'ai-provider-swarm-gateway[flutter]'
ai-provider-gateway mcp-toolbox serve
```

The read-only helper commands (`tools`, `doctor`, `config`) are safe to run
without live provider credentials. The `serve` command imports the MCP SDK only
when explicitly invoked.

Path-based MCP tools fail closed unless `AI_PROVIDER_GATEWAY_MCP_ALLOWED_ROOTS`
is set. Use a comma-separated list for Flutter app roots:

```bash
export AI_PROVIDER_GATEWAY_MCP_ALLOWED_ROOTS="$HOME/code/app1,$HOME/code/app2"
uv run ai-provider-gateway mcp-toolbox tools --json
uv run ai-provider-gateway mcp-toolbox doctor --json
uv run ai-provider-gateway mcp-toolbox config
uv run ai-provider-gateway mcp-toolbox serve
```

MCP clients can then call `flutter_project_summary` and `run_flutter_analyze`
for paths under the configured roots. Calls outside those roots return
`workspace_not_allowed` and never execute `flutter analyze`.

## Flutter local workflow

```bash
pip install 'ai-provider-swarm-gateway[flutter]'
uv run ai-provider-gateway tenants pool init
uv run ai-provider-gateway tenants pool add 9router dev --secret "$AI_PROVIDER_GATEWAY_9ROUTER_API_KEY"
uv run ai-provider-gateway tenants pool list
export AI_PROVIDER_GATEWAY_9ROUTER_API_KEY="..."
export AI_PROVIDER_GATEWAY_MCP_ALLOWED_ROOTS="$HOME/code/my_flutter_app"
uv run ai-provider-gateway mcp-toolbox serve
```

Back up both `~/.ai_provider_gateway/vault.key` and
`~/.ai_provider_gateway/secrets.json.enc`; the encrypted vault is not useful
without its key.

## Command surface

Core commands:

- `version` — print installed package versions.
- `providers list` — inspect the packaged provider registry.
- `route` — route a prompt through the gateway graph.
- `swarm` — run the hive-swarm orchestration path.
- `inspect-state` — print `GatewayState` fields for debugging.
- `dashboard` — launch the optional Textual monitoring dashboard.

Quota and tenant commands:

- `quota show` — inspect local quota usage.
- `quota increment` — increment local quota counters.
- `quota reset` — reset one provider/window counter; prompts unless `--yes` is used.
- `quota set-reset` — set a reset timestamp.
- `tenants list` — list tenant usage stores under the default base path.
- `tenants storage-path` — print the canonical tenant usage path.

Secret and audit commands:

- `tenants pool init` — create a local Fernet vault key file.
- `tenants pool add` — add/update one encrypted provider account secret.
- `tenants pool list` — list account IDs; secret values are never printed.
- `tenants pool sync --push/--pull` — copy the encrypted vault blob to/from S3.
- `auth import-browser` — explicitly import supported browser session cookies into the vault.
- `audit verify` — verify local JSONL or S3 audit chains.
- `audit restore` — request S3 Glacier restore for archived audit partitions.

## Safety notes

- `--thread-id` and S3 `audit verify --swarm-id` accept only `a-z`, `A-Z`, `0-9`, `_`, and `-` up to 128 chars.
- `AI_PROVIDER_GATEWAY_USAGE_PATH` overrides quota storage. In production wrappers, point it at a persistent state directory and do not source it from untrusted input.
- Set `AI_PROVIDER_GATEWAY_STATE_DIR` to require `--storage` and `AI_PROVIDER_GATEWAY_USAGE_PATH` to resolve inside that directory.
- `tenants pool sync --pull` downloads to a temporary file and atomically replaces the local vault. If the vault already exists, confirm overwrite or pass `--yes`.
- `tenants pool sync --pull` decrypt-checks the downloaded vault before replacement when a vault key is available; corrupt downloads keep the existing local vault.
- Prefer `AI_PROVIDER_GATEWAY_9ROUTER_API_KEY` for 9router. `OPENAI_API_KEY` is used by 9router only when `AI_PROVIDER_GATEWAY_9ROUTER_ALLOW_OPENAI_KEY` is truthy.
- Use `AI_PROVIDER_GATEWAY_9ROUTER_ALLOWED_HOSTS` to pin allowed 9router hosts when using a non-local base URL.
- Treat `mcp-toolbox serve` as a local developer surface; path-based tools require `AI_PROVIDER_GATEWAY_MCP_ALLOWED_ROOTS`.
