"""Tests for interactive HITL prompt — mocked stdin."""

from __future__ import annotations

from typing import Any

import pytest

from ai_provider_swarm_gateway.cli import _interactive_hitl_prompt


def _payload(token: str = "tok-12345"):
    return {
        "swarm_id": "s1",
        "proposed_action_preview": "do the thing",
        "risk_score": 0.85,
        "agreement_fraction": 0.6,
        "protocol": "raft",
        "decision_token_required": token,
    }


def test_approve_via_y(monkeypatch):
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "y")
    out = _interactive_hitl_prompt("s1", _payload())
    assert out is not None
    assert out["decision"] == "approve"
    assert out["decision_token"] == "tok-12345"


def test_approve_via_yes(monkeypatch):
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "yes")
    out = _interactive_hitl_prompt("s1", _payload())
    assert out["decision"] == "approve"


def test_approve_via_approve_word(monkeypatch):
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "approve")
    out = _interactive_hitl_prompt("s1", _payload())
    assert out["decision"] == "approve"


def test_deny_via_n(monkeypatch):
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "n")
    out = _interactive_hitl_prompt("s1", _payload())
    assert out["decision"] == "deny"


def test_deny_via_deny_word(monkeypatch):
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "deny")
    out = _interactive_hitl_prompt("s1", _payload())
    assert out["decision"] == "deny"


def test_unknown_response_returns_none(monkeypatch):
    """Caller treats None as deny."""
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "maybe")
    out = _interactive_hitl_prompt("s1", _payload())
    assert out is None


def test_token_echoed_verbatim(monkeypatch):
    """Single-use guard: the issued token must echo back exactly."""
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "y")
    payload = _payload(token="exactly-this-token-abcdef")
    out = _interactive_hitl_prompt("s1", payload)
    assert out["decision_token"] == "exactly-this-token-abcdef"


def test_reviewer_id_from_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_REVIEWER_ID", "alice@example.com")
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "y")
    out = _interactive_hitl_prompt("s1", _payload())
    assert out["reviewer_id"] == "alice@example.com"


def test_reviewer_id_falls_back_to_user_env(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER_GATEWAY_REVIEWER_ID", raising=False)
    monkeypatch.setenv("USER", "bob")
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "y")
    out = _interactive_hitl_prompt("s1", _payload())
    assert out["reviewer_id"] == "bob"


def test_eof_returns_none(monkeypatch):
    """Operator hits Ctrl-D / pipe closes → treated as deny by caller."""

    def boom(*a, **kw):
        raise EOFError()

    monkeypatch.setattr("typer.prompt", boom)
    out = _interactive_hitl_prompt("s1", _payload())
    assert out is None


def test_keyboard_interrupt_returns_none(monkeypatch):
    def boom(*a, **kw):
        raise KeyboardInterrupt()

    monkeypatch.setattr("typer.prompt", boom)
    out = _interactive_hitl_prompt("s1", _payload())
    assert out is None
