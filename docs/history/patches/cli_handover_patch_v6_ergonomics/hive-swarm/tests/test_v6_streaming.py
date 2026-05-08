"""Tests for streaming dispatch (StubDispatcher.dispatch_stream + GatewayDispatcher.dispatch_stream)."""
from typing import Any

import pytest

from swarm.llm import dispatch as dispatch_mod
from swarm.llm.dispatch import (
    GatewayDispatcher,
    StreamChunk,
    StubDispatcher,
    WorkerLLMError,
    _normalise_stream_chunk,
)
from swarm.models.agent import AgentState, WorkerResult
from swarm.models.config import SwarmConfig
from swarm.models.task import QueenDirective, SwarmTask
from swarm.nodes.queen import _llm_settings_from_config
from swarm.nodes.worker import worker_node


# ── StreamChunk shape ────────────────────────────────────────────────────

def test_stream_chunk_dataclass():
    c = StreamChunk(delta="hello", text="hello", index=0)
    assert c.delta == "hello"
    assert c.done is False
    assert c.finish_reason == ""


# ── _normalise_stream_chunk ──────────────────────────────────────────────

def test_normalise_string_chunk():
    delta, finish = _normalise_stream_chunk("hello")
    assert delta == "hello"
    assert finish == ""


def test_normalise_dict_with_delta_field():
    delta, finish = _normalise_stream_chunk({"delta": "tok", "finish_reason": "stop"})
    assert delta == "tok"
    assert finish == "stop"


def test_normalise_openai_sse_shape():
    raw = {
        "choices": [{
            "delta": {"content": "world"},
            "finish_reason": None,
        }]
    }
    delta, finish = _normalise_stream_chunk(raw)
    assert delta == "world"


def test_normalise_openai_sse_with_finish():
    raw = {
        "choices": [{
            "delta": {"content": "."},
            "finish_reason": "stop",
        }]
    }
    delta, finish = _normalise_stream_chunk(raw)
    assert delta == "."
    assert finish == "stop"


def test_normalise_object_with_delta_attr():
    class C:
        delta = "via-attr"
        finish_reason = "stop"
    delta, finish = _normalise_stream_chunk(C())
    assert delta == "via-attr"
    assert finish == "stop"


def test_normalise_none_returns_empty():
    assert _normalise_stream_chunk(None) == ("", "")


def test_normalise_unknown_returns_empty():
    assert _normalise_stream_chunk(42) == ("", "")


# ── StubDispatcher.dispatch_stream ───────────────────────────────────────

def test_stub_dispatch_stream_emits_single_done_chunk():
    d = StubDispatcher()
    chunks = list(d.dispatch_stream("coder", "implement add"))
    assert len(chunks) == 1
    assert chunks[0].done is True
    assert chunks[0].text == "[CODER] Implementation for: implement add"
    assert chunks[0].finish_reason == "stop"


# ── GatewayDispatcher.dispatch_stream ────────────────────────────────────

class _FakeStreamingAdapter:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls: list[dict[str, Any]] = []

    def is_configured(self):
        return True

    def chat(self, *, messages, max_tokens, temperature, model=None):
        # Only used for fallback path tests
        self.calls.append({"method": "chat", "messages": messages})
        return {
            "model": "fake",
            "choices": [{"message": {"content": "non-stream"}, "finish_reason": "stop"}],
        }

    def chat_stream(self, *, messages, max_tokens, temperature, model=None):
        self.calls.append({"method": "chat_stream", "model": model})
        for c in self.chunks:
            yield c


def test_gateway_dispatch_stream_collects_chunks():
    adapter = _FakeStreamingAdapter(chunks=[
        {"delta": "Hello", "finish_reason": ""},
        {"delta": " world", "finish_reason": ""},
        {"delta": "!", "finish_reason": "stop"},
    ])
    d = GatewayDispatcher(default_provider="x", adapter_factory=lambda pid: adapter)
    chunks = list(d.dispatch_stream("coder", "say hi"))

    # Stream chunks (non-done) + 1 done sentinel
    assert chunks[-1].done is True
    assert chunks[-1].text == "Hello world!"
    assert chunks[-1].finish_reason == "stop"


def test_gateway_dispatch_stream_intermediate_chunks_have_running_text():
    adapter = _FakeStreamingAdapter(chunks=[
        {"delta": "A", "finish_reason": ""},
        {"delta": "B", "finish_reason": ""},
    ])
    d = GatewayDispatcher(default_provider="x", adapter_factory=lambda pid: adapter)
    chunks = list(d.dispatch_stream("coder", "x"))
    # Intermediate
    assert chunks[0].text == "A"
    assert chunks[1].text == "AB"
    # Final sentinel
    assert chunks[-1].done is True


def test_gateway_dispatch_stream_falls_back_when_no_chat_stream():
    """Adapter without chat_stream → falls back to dispatch_full + 1 chunk."""
    class NoStream:
        def is_configured(self): return True
        def chat(self, *, messages, max_tokens, temperature, model=None):
            return {"choices": [{"message": {"content": "non-streamed"},
                                 "finish_reason": "stop"}]}

    d = GatewayDispatcher(default_provider="x", adapter_factory=lambda pid: NoStream())
    chunks = list(d.dispatch_stream("coder", "x"))
    assert len(chunks) == 1
    assert chunks[0].done is True
    assert chunks[0].text == "non-streamed"


def test_gateway_dispatch_stream_unconfigured_raises():
    class Unc:
        def is_configured(self): return False
    d = GatewayDispatcher(default_provider="x", adapter_factory=lambda pid: Unc())
    with pytest.raises(WorkerLLMError, match="not configured"):
        list(d.dispatch_stream("coder", "x"))


def test_gateway_dispatch_stream_chat_stream_error_raises_typed():
    class Boom:
        def is_configured(self): return True
        def chat_stream(self, **kw):
            raise RuntimeError("simulated stream failure")
    d = GatewayDispatcher(default_provider="x", adapter_factory=lambda pid: Boom())
    with pytest.raises(WorkerLLMError, match="chat_stream"):
        list(d.dispatch_stream("coder", "x"))


def test_gateway_dispatch_stream_passes_per_role_model():
    adapter = _FakeStreamingAdapter(chunks=[{"delta": "x", "finish_reason": "stop"}])
    d = GatewayDispatcher(
        default_provider="x",
        default_model="default",
        role_model_overrides={"coder": "specific-model"},
        adapter_factory=lambda pid: adapter,
    )
    list(d.dispatch_stream("coder", "task"))
    # Adapter recorded the model kwarg
    chat_stream_call = next(c for c in adapter.calls if c["method"] == "chat_stream")
    assert chat_stream_call["model"] == "specific-model"


# ── End-to-end: worker_node with stream_enabled=True ─────────────────────

def _make_agent(role="coder", task="x", config=None):
    cfg = config or SwarmConfig(
        llm_backend="gateway",
        llm_stream_enabled=True,
    )
    settings = _llm_settings_from_config(cfg)
    shared = {
        "iteration": 1, "objective": "x",
        "retrieved_patterns": [], "llm_settings": settings,
    }
    swarm_task = SwarmTask(
        task_id="t1", description=task, priority="high",
        assigned_to=f"{role}-1", required_role=role,
    )
    swarm_task.assign(f"{role}-1")
    directive = QueenDirective(
        directive_id="dir-t1", task=swarm_task,
        assigned_agent_id=f"{role}-1", assigned_role=role,
        objective_hash="deadbeefcafebabe",
        shared_context=shared,
    )
    return AgentState(
        agent_id=f"{role}-1", role=role,
        assigned_task_id="t1", task_description=task,
        task_context=directive.model_dump(mode="json"),
    )


def test_worker_consumes_stream_when_enabled(monkeypatch):
    adapter = _FakeStreamingAdapter(chunks=[
        {"delta": "def add(a, b):", "finish_reason": ""},
        {"delta": "\n    return a + b", "finish_reason": "stop"},
    ])
    monkeypatch.setattr(
        dispatch_mod, "_default_adapter_factory",
        lambda pid: adapter,
    )
    agent = _make_agent()
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is True
    assert "def add" in r.output
    assert r.metadata.get("llm_streamed") is True
    # Adapter was called via chat_stream, not chat
    assert any(c["method"] == "chat_stream" for c in adapter.calls)
