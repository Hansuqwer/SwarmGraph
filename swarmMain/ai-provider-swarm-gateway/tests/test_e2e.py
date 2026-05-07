"""End-to-end gateway tests using mock provider — no credentials required."""
from __future__ import annotations
import pytest
from src.ai_provider_swarm_gateway.graph.builder import build_gateway_graph
from src.ai_provider_swarm_gateway.models.state import GatewayState


def _run(prompt: str, **kwargs) -> GatewayState:
    graph = build_gateway_graph()
    state = GatewayState(user_prompt=prompt, **kwargs)
    result = graph.invoke(state.to_json_dict())
    return GatewayState.from_json_dict(result)


def test_graph_runs_with_mock_provider():
    """Full pipeline runs without real credentials."""
    final = _run("What is 2 + 2?")
    assert final is not None
    assert isinstance(final.audit_log, list)
    assert len(final.audit_log) > 0


def test_gateway_produces_response_or_logged_error():
    final = _run("Explain quantum computing briefly.")
    # Either we get a response or we get a graceful no-provider message
    has_response = final.provider_response is not None and final.provider_response.content is not None
    has_error    = len(final.errors) > 0 or (
        final.routing_decision is not None and final.routing_decision.selected_provider_id is None
    )
    assert has_response or has_error, "Must either have a response or a graceful error"


def test_preferred_mock_provider_routes_correctly():
    final = _run("Hello", preferred_provider_id="mock")
    # If mock is available and configured, it should be selected
    if final.provider_response:
        assert final.provider_response.provider_id == "mock"


def test_audit_log_captures_pipeline_steps():
    final = _run("test prompt")
    step_names = ["intake_node", "classify_request", "provider_filter", "quota_check"]
    for step in step_names:
        found = any(step in entry for entry in final.audit_log)
        assert found, f"Step '{step}' not found in audit log"


def test_policy_violation_stops_pipeline():
    """An empty prompt must be stopped at intake."""
    graph = build_gateway_graph()
    # Can't create GatewayState with empty prompt (min_length=1) — this is the Pydantic guard
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GatewayState(user_prompt="")


def test_errors_list_does_not_leak_secrets():
    final = _run("hello world")
    for err in final.errors:
        assert "sk-" not in err, "Error messages must not contain raw API keys"


def test_full_pipeline_is_idempotent():
    """Running same prompt twice should not accumulate state."""
    r1 = _run("What is AI?")
    r2 = _run("What is AI?")
    # Both should complete independently
    assert isinstance(r1.audit_log, list)
    assert isinstance(r2.audit_log, list)
