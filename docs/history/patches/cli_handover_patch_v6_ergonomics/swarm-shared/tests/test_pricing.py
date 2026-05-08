"""Tests for swarm_shared.pricing."""
import json
from pathlib import Path

import pytest

from swarm_shared.pricing import (
    DEFAULT_PRICING_TABLE,
    PricingEntry,
    PricingTable,
    estimate_cost,
)


# ── PricingEntry ─────────────────────────────────────────────────────────

def test_entry_is_free_when_both_zero():
    e = PricingEntry("free-model", 0.0, 0.0)
    assert e.is_free


def test_entry_not_free_when_priced():
    e = PricingEntry("paid", 0.001, 0.002)
    assert not e.is_free


# ── Lookup precedence ────────────────────────────────────────────────────

def test_lookup_exact_match():
    e = DEFAULT_PRICING_TABLE.lookup("claude-opus-4-7")
    assert e is not None
    assert e.input_per_1k > 0


def test_lookup_strips_free_suffix():
    e = DEFAULT_PRICING_TABLE.lookup("kc/kilo-auto/free")
    assert e is not None
    assert e.is_free


def test_lookup_provider_glob_fallback():
    """stepfun/step-3.5-flash falls through to stepfun/*."""
    # Direct first
    e1 = DEFAULT_PRICING_TABLE.lookup("stepfun/step-3.5-flash")
    assert e1 is not None
    # Unknown stepfun model falls back to glob
    e2 = DEFAULT_PRICING_TABLE.lookup("stepfun/some-future-model")
    assert e2 is not None
    assert e2.is_free


def test_lookup_unknown_returns_none():
    assert DEFAULT_PRICING_TABLE.lookup("unknown-vendor/secret-model") is None


def test_lookup_empty_returns_none():
    assert DEFAULT_PRICING_TABLE.lookup("") is None


# ── Cost estimation ──────────────────────────────────────────────────────

def test_estimate_cost_free_model():
    cost = estimate_cost("kc/kilo-auto/free", 10_000, 20_000)
    assert cost == 0.0


def test_estimate_cost_anthropic_opus():
    # Opus 4.7: $5/MTok in, $25/MTok out
    # 1000 input + 500 output → 0.005 + 0.0125 = 0.0175
    cost = estimate_cost("claude-opus-4-7", 1000, 500)
    assert cost == pytest.approx(0.0175)


def test_estimate_cost_anthropic_sonnet():
    # Sonnet 4.6: $3/MTok in, $15/MTok out
    cost = estimate_cost("claude-sonnet-4-6", 1000, 500)
    assert cost == pytest.approx(0.0105)


def test_estimate_cost_unknown_returns_none():
    assert estimate_cost("phantom-model", 100, 200) is None


def test_estimate_cost_zero_tokens_zero_cost():
    cost = estimate_cost("claude-opus-4-7", 0, 0)
    assert cost == 0.0


def test_estimate_cost_rounded_6_decimals():
    """Tiny token counts should not produce float-noise results."""
    cost = estimate_cost("claude-haiku-4-5", 1, 1)
    assert cost is not None
    # round to 6 places
    assert isinstance(cost, float)
    s = f"{cost:.10f}"
    # at most 6 non-zero post-decimal digits
    decimal = s.split(".")[1]
    trailing_significant = decimal.rstrip("0")
    assert len(trailing_significant) <= 6


# ── Table construction ──────────────────────────────────────────────────

def test_from_dict_round_trip():
    raw = {
        "entries": {
            "test-model": {"input_per_1k": 0.01, "output_per_1k": 0.05, "notes": "test"},
        }
    }
    t = PricingTable.from_dict(raw)
    e = t.lookup("test-model")
    assert e is not None
    assert e.input_per_1k == 0.01
    assert e.notes == "test"


def test_from_json_file(tmp_path: Path):
    fp = tmp_path / "pricing.json"
    fp.write_text(json.dumps({
        "entries": {
            "custom/model": {"input_per_1k": 0.02, "output_per_1k": 0.08},
        }
    }))
    t = PricingTable.from_json_file(fp)
    cost = t.estimate_cost("custom/model", 1000, 1000)
    assert cost == pytest.approx(0.10)


def test_default_table_includes_anthropic_lineup():
    """Sanity: every May-2026 Anthropic model is priced."""
    for model in ("claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"):
        assert DEFAULT_PRICING_TABLE.lookup(model) is not None


def test_default_table_includes_free_providers():
    for model in ("kc/kilo-auto/free", "mock", "stub:deterministic", "ollama_local"):
        e = DEFAULT_PRICING_TABLE.lookup(model)
        assert e is not None
        assert e.is_free


def test_custom_table_override_via_estimate_cost():
    custom = PricingTable.from_dict({
        "entries": {
            "claude-opus-4-7": {"input_per_1k": 0.001, "output_per_1k": 0.002},
        }
    })
    # Default would compute $0.0175; custom gives $0.002
    default_cost = estimate_cost("claude-opus-4-7", 1000, 500)
    custom_cost = estimate_cost("claude-opus-4-7", 1000, 500, table=custom)
    assert default_cost != custom_cost
    assert custom_cost == pytest.approx(0.001 + 0.001)
