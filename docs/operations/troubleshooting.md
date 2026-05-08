# Troubleshooting

Common checks:

- `uv run ai-provider-gateway providers list`
- `uv run ai-provider-gateway quota show --json`
- `uv run pytest packages/hive-swarm/tests/test_v8_streaming_hitl.py`
- `uv run ai-provider-gateway audit verify audit.jsonl`

LangGraph `allowed_objects` deprecation warnings are currently harmless.
