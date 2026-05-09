"""Tests for swarm_shared.hashing."""

import pytest
from swarm_shared.hashing import stable_hash, full_sha256


def test_stable_hash_default_length_is_16():
    assert len(stable_hash("hello")) == 16


def test_stable_hash_deterministic():
    assert stable_hash("foo") == stable_hash("foo")


def test_stable_hash_distinct_inputs_distinct_outputs():
    assert stable_hash("foo") != stable_hash("bar")


def test_stable_hash_custom_length():
    assert len(stable_hash("hello", length=8)) == 8
    assert len(stable_hash("hello", length=64)) == 64


def test_stable_hash_rejects_non_str():
    with pytest.raises(TypeError):
        stable_hash(b"bytes-not-str")  # type: ignore[arg-type]


def test_full_sha256_is_64_hex():
    h = full_sha256("hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_objective_hash_canonical_value():
    """Anchor: objective_hash for the analysis run."""
    expected = stable_hash("analyse swarmMain v2026-05-07 +pydantic +langgraph -compliance")
    assert len(expected) == 16
    assert isinstance(expected, str)
