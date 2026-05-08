# Patch — register `9router` in `_get_adapter`

File: `src/ai_provider_swarm_gateway/graph/nodes.py`

## Change 1 — add the import

Find the imports block at the top of `_get_adapter` (or the module top, whichever
your local upstream layout uses). Add:

```python
from ..providers.nine_router_adapter import NineRouterAdapter
```

If your version lazily imports adapters inside `_get_adapter` itself, add the
import there alongside `from ..providers.openai_adapter import OpenAIAdapter`.

## Change 2 — add the registry entry

In the `adapters` dict inside `_get_adapter`, add ONE line:

```python
def _get_adapter(provider_id: str) -> ProviderAdapter:
    from ..providers.openai_adapter import OpenAIAdapter
    from ..providers.anthropic_adapter import AnthropicAdapter
    from ..providers.google_adapter import GoogleAdapter
    from ..providers.groq_adapter import GroqAdapter
    from ..providers.deepseek_adapter import DeepSeekAdapter
    from ..providers.qwen_adapter import QwenAdapter
    from ..providers.glm_adapter import GLMAdapter
    from ..providers.kimi_adapter import KimiAdapter
    from ..providers.openrouter_adapter import OpenRouterAdapter
    from ..providers.nine_router_adapter import NineRouterAdapter   # ← ADD
    from ..providers.mock_adapter import MockAdapter

    adapters: dict[str, ProviderAdapter] = {
        "openai": OpenAIAdapter(),
        "anthropic": AnthropicAdapter(),
        "google_gemini": GoogleAdapter(),
        "groq": GroqAdapter(),
        "deepseek": DeepSeekAdapter(),
        "qwen": QwenAdapter(),
        "zhipu_glm": GLMAdapter(),
        "moonshot_kimi": KimiAdapter(),
        "openrouter": OpenRouterAdapter(),
        "9router": NineRouterAdapter(),                              # ← ADD
        "mock": MockAdapter(),
    }
    return adapters.get(provider_id, MockAdapter())
```

That's it — two lines.

## Verify the registration

```bash
.venv/bin/python -c "
from ai_provider_swarm_gateway.graph.nodes import _get_adapter
a = _get_adapter('9router')
print(type(a).__name__, '— configured:', a.is_configured())
"
# expected:
#   NineRouterAdapter — configured: True   (if any of the API key env vars are set)
#   NineRouterAdapter — configured: False  (otherwise)
```
