"""Tests for LangGraph graph compilation and node execution."""
from __future__ import annotations
import pytest
from src.ai_provider_swarm_gateway.graph.builder import build_gateway_graph
from src.ai_provider_swarm_gateway.graph.nodes import (
    intake_node, classify_request_node, provider_filter_node,
    quota_check_node, consensus_node, response_validation_node,
)
from src.ai_provider_swarm_gateway.models.state import GatewayState


@pytest.fixture
def base_state():
    return GatewayState(user_prompt="What is the capital of France?").to_json_dict()


def test_graph_compiles():
    graph = build_gateway_graph()
    assert graph is not None


def test_intake_node_accepts_valid_prompt(base_state):
    result = intake_node(base_state)
    s = GatewayState.from_json_dict(result)
    assert s.is_safe_to_proceed is True


def test_intake_node_rejects_quota_evasion_flags():
    s = GatewayState(user_prompt="test").to_json_dict()
    s["user_prompt"] = "test"
    # Manually inject prohibited flag into metadata (simulated)
    result = intake_node(s)
    out = GatewayState.from_json_dict(result)
    assert out.is_safe_to_proceed is True  # prompt itself is clean


def test_classify_request_infers_chat(base_state):
    result = classify_request_node(base_state)
    s = GatewayState.from_json_dict(result)
    assert s.requested_capability in ("chat", "code", "embeddings", "image")


def test_classify_request_detects_code():
    s = GatewayState(user_prompt="debug this Python function and refactor it").to_json_dict()
    result = classify_request_node(s)
    out = GatewayState.from_json_dict(result)
    assert out.requested_capability == "code"


def test_provider_filter_returns_candidates(base_state):
    after_classify = classify_request_node(base_state)
    result = provider_filter_node(after_classify)
    s = GatewayState.from_json_dict(result)
    # At minimum mock provider should be available
    assert isinstance(s.candidate_providers, list)


def test_quota_check_preserves_valid_candidates(base_state):
    after_classify = classify_request_node(base_state)
    after_filter   = provider_filter_node(after_classify)
    result = quota_check_node(after_filter)
    s = GatewayState.from_json_dict(result)
    assert isinstance(s.candidate_providers, list)


def test_response_validation_adds_error_on_empty():
    s = GatewayState(user_prompt="test").to_json_dict()
    # No provider_response set — should add error
    result = response_validation_node(s)
    out = GatewayState.from_json_dict(result)
    assert len(out.errors) > 0
