"""Worker LLM dispatch layer (v8)."""
from .dispatch import (
    DEFAULT_SETTINGS,
    GatewayDispatcher,
    StreamChunk,
    StreamingHITLInterrupt,
    StubDispatcher,
    WorkerLLMDispatcher,
    WorkerLLMError,
    WorkerLLMResponse,
    build_dispatcher,
    estimate_call_cost,
    resolve_llm_settings,
)
from .embeddings import (
    EmbeddingProvider,
    GatewayEmbedder,
    HashEmbedder,
    NullEmbedder,
    OpenAIEmbeddingAdapter,
    cosine_similarity,
    default_embedder_from_env,
    get_default_embedder,
    set_default_embedder,
)
from .prompts import get_system_prompt

__all__ = [
    # Dispatch
    "WorkerLLMDispatcher",
    "WorkerLLMResponse",
    "StreamChunk",
    "StreamingHITLInterrupt",
    "StubDispatcher",
    "GatewayDispatcher",
    "WorkerLLMError",
    "build_dispatcher",
    "estimate_call_cost",
    "resolve_llm_settings",
    "get_system_prompt",
    "DEFAULT_SETTINGS",
    # Embeddings
    "EmbeddingProvider",
    "NullEmbedder",
    "HashEmbedder",
    "GatewayEmbedder",
    "OpenAIEmbeddingAdapter",
    "cosine_similarity",
    "get_default_embedder",
    "set_default_embedder",
    "default_embedder_from_env",
]
