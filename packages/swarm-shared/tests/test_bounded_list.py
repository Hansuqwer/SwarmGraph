"""Tests for swarm_shared.bounded_list."""

import pytest
from pydantic import BaseModel, Field, field_validator

from swarm_shared.bounded_list import CappedListConfig, bounded_list_validator, cap_list


def test_cap_list_no_op_when_under_limit():
    items = [1, 2, 3]
    cfg = CappedListConfig(max_len=10)
    assert cap_list(items, cfg) == [1, 2, 3]


def test_cap_list_tail_keeps_last_n():
    items = list(range(100))
    cfg = CappedListConfig(max_len=10, keep_strategy="tail")
    assert cap_list(items, cfg) == list(range(90, 100))


def test_cap_list_head_keeps_first_n():
    items = list(range(100))
    cfg = CappedListConfig(max_len=10, keep_strategy="head")
    assert cap_list(items, cfg) == list(range(10))


def test_cap_list_head_plus_tail_keeps_first_and_last():
    items = list(range(100))
    cfg = CappedListConfig(max_len=10, keep_strategy="head_plus_tail")
    out = cap_list(items, cfg)
    assert out[0] == 0  # original first preserved
    assert out[-1] == 99  # most recent preserved
    assert len(out) == 10


def test_cap_list_does_not_mutate_input():
    items = list(range(100))
    cfg = CappedListConfig(max_len=10)
    cap_list(items, cfg)
    assert items == list(range(100))


def test_invalid_max_len_rejected():
    with pytest.raises(ValueError):
        CappedListConfig(max_len=0)


def test_invalid_strategy_rejected():
    with pytest.raises(ValueError):
        CappedListConfig(max_len=10, keep_strategy="middle")


def test_bounded_list_validator_caps_pydantic_field():
    cfg = CappedListConfig(max_len=3, keep_strategy="tail")

    class Example(BaseModel):
        items: list[int] = Field(default_factory=list)

        _cap_items = field_validator("items")(bounded_list_validator("items", cfg))

    assert Example(items=[1, 2, 3, 4, 5]).items == [3, 4, 5]
