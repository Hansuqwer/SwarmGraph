"""Worker LLM dispatch layer.

Public API:
  - WorkerLLMDispatcher (Protocol)
  - StubDispatcher           — deterministic; default for back-compat
  - GatewayDispatcher        — routes via ai-provider-swarm-gateway adapters
  - WorkerLLMError           — typed exception (becomes WorkerResult.error_message)
  - build_dispatcher(settings) -> WorkerLLMDispatcher
  - resolve_llm_settings(task_context, role) -> dict
  - get_system_prompt(role) -> str
  - DEFAULT_SETTINGS

Keep imports cheap: importing `swarm.llm` must not pull
ai-provider-swarm-gateway, so stub-mode users with no gateway installed are
unaffected.
"""
from .dispatch import (
    DEFAULT_SETTINGS,
    GatewayDispatcher,
    StubDispatcher,
    WorkerLLMDispatcher,
    WorkerLLMError,
    build_dispatcher,
    resolve_llm_settings,
)
from .prompts import get_system_prompt

__all__ = [
    "WorkerLLMDispatcher",
    "StubDispatcher",
    "GatewayDispatcher",
    "WorkerLLMError",
    "build_dispatcher",
    "resolve_llm_settings",
    "get_system_prompt",
    "DEFAULT_SETTINGS",
]
