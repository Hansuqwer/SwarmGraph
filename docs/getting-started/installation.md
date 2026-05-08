# Installation

```bash
git clone https://github.com/Hansuqwer/SwarmGraph.git
cd SwarmGraph
uv sync --all-extras --dev
```

Run tests:

```bash
uv run pytest packages/swarm-shared/tests packages/hive-swarm/tests packages/ai-provider-swarm-gateway/tests
```

The default backend is stub mode; no API key is required.
