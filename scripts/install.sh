#!/usr/bin/env sh
set -eu

VERSION="0.8.1"
TARGET="${TARGET:-./SwarmGraph}"
BASE="https://github.com/Hansuqwer/SwarmGraph/releases/download/v${VERSION}"

FLUTTER=0
for arg in "$@"; do
  case "$arg" in
    --flutter)
      FLUTTER=1
      ;;
    -h|--help)
      echo "Usage: install.sh [--flutter]"
      echo "  no flag     Install SwarmGraph with standard extras"
      echo "  --flutter   Also install MCP toolbox for Flutter workflows"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      exit 2
      ;;
  esac
done

mkdir -p "$TARGET"
cd "$TARGET"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download SwarmGraph. Install curl, then rerun this installer."
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -fL --retry 3 --retry-delay 2 https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
  sh /tmp/uv-install.sh
  rm -f /tmp/uv-install.sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  hash -r 2>/dev/null || true
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv install failed. Install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

echo "Creating Python 3.11 environment..."
uv venv --python 3.11 .venv

STANDARD_EXTRAS="textual>=0.80,<1 plotext>=5,<6 psutil>=5,<8 fastapi>=0.115,<1 uvicorn>=0.30,<1 prometheus-client>=0.20,<1 pyyaml>=6,<7 cryptography>=42,<47 browser-cookie3>=0.20,<1 langgraph>=0.3,<2 langgraph-checkpoint>=4.0.0,<5 langgraph-checkpoint-sqlite>=3.0.1,<4"

if [ "$FLUTTER" = "1" ]; then
  STANDARD_EXTRAS="$STANDARD_EXTRAS mcp>=1.9,<2"
  echo "Flutter mode: including MCP toolbox."
  if ! command -v flutter >/dev/null 2>&1; then
    echo "Note: flutter CLI not found. Install Flutter separately for Flutter workflows."
  fi
fi

echo "Installing SwarmGraph ${VERSION}..."
uv pip install --python .venv/bin/python \
  "${BASE}/swarm_shared-${VERSION}-py3-none-any.whl" \
  "${BASE}/hive_swarm-${VERSION}-py3-none-any.whl" \
  "${BASE}/ai_provider_swarm_gateway-${VERSION}-py3-none-any.whl" \
  $STANDARD_EXTRAS

cat > swarmgraph <<'EOF'
#!/usr/bin/env sh
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$DIR/.venv/bin/swarmgraph" "$@"
EOF
chmod +x swarmgraph

./swarmgraph version || {
  echo "Install completed but smoke check failed."
  exit 1
}

echo ""
echo "Installed in $(pwd)"
echo "Run:"
echo "  cd $(pwd)"
echo "  ./swarmgraph --help"
echo "  ./swarmgraph dashboard"
if [ "$FLUTTER" = "1" ]; then
  echo "  ./swarmgraph mcp-toolbox --help"
fi
