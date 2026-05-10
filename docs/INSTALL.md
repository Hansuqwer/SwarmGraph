# Install SwarmGraph

SwarmGraph can be installed from GitHub release wheels without PyPI. The installer creates a local `SwarmGraph/` folder with a private `.venv/` and a `./swarmgraph` launcher. It does not modify your shell profile or install anything globally except `uv` if missing.

## Quick Install

```bash
curl -fsSL https://github.com/Hansuqwer/SwarmGraph/releases/download/v0.8.1/install.sh | sh
```

Then run:

```bash
cd SwarmGraph
./swarmgraph --help
```

## Flutter Workflow

If you build Flutter apps and want the MCP toolbox:

```bash
curl -fsSL https://github.com/Hansuqwer/SwarmGraph/releases/download/v0.8.1/install.sh | sh -s -- --flutter
```

The Flutter mode installs the Python MCP dependency. It does not install Flutter itself. You must install the `flutter` CLI separately and keep it on your `PATH`.

## Custom Folder

```bash
TARGET="$HOME/tools/SwarmGraph" sh install.sh
```

Or with the remote installer:

```bash
curl -fsSL https://github.com/Hansuqwer/SwarmGraph/releases/download/v0.8.1/install.sh | TARGET="$HOME/tools/SwarmGraph" sh
```

## Inspect Then Run

For a safer install, download and inspect the script first:

```bash
curl -fsSL https://github.com/Hansuqwer/SwarmGraph/releases/download/v0.8.1/install.sh -o install.sh
less install.sh
sh install.sh
```

Flutter mode:

```bash
sh install.sh --flutter
```

## Manual Install

```bash
mkdir SwarmGraph
cd SwarmGraph
uv venv --python 3.11
uv pip install --python .venv/bin/python \
  https://github.com/Hansuqwer/SwarmGraph/releases/download/v0.8.1/swarm_shared-0.8.1-py3-none-any.whl \
  https://github.com/Hansuqwer/SwarmGraph/releases/download/v0.8.1/hive_swarm-0.8.1-py3-none-any.whl \
  https://github.com/Hansuqwer/SwarmGraph/releases/download/v0.8.1/ai_provider_swarm_gateway-0.8.1-py3-none-any.whl
```

## Requirements

- macOS or Linux shell.
- `curl`.
- Python `>=3.11,<3.14` installed or installable by `uv`.
- `uv`; the installer installs it if missing.
- Flutter CLI only if you use `--flutter` workflows.

## Run

```bash
cd SwarmGraph
./swarmgraph --help
./swarmgraph version
./swarmgraph dashboard
./swarmgraph audit --help
```

## Uninstall

```bash
rm -rf SwarmGraph
```

Do not commit provider tokens, vault keys, cookies, or `.env` files.
