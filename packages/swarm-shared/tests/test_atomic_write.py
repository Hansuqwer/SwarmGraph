"""Tests for swarm_shared.atomic_write."""

import json
import os
from pathlib import Path

import pytest

from swarm_shared.atomic_write import atomic_write_json, atomic_write_text


def test_atomic_write_text_creates_file(tmp_path: Path):
    target = tmp_path / "out.txt"
    atomic_write_text(target, "hello\n")
    assert target.read_text() == "hello\n"


def test_atomic_write_json_round_trip(tmp_path: Path):
    target = tmp_path / "data.json"
    atomic_write_json(target, {"a": 1, "b": [1, 2, 3]})
    assert json.loads(target.read_text()) == {"a": 1, "b": [1, 2, 3]}


def test_atomic_write_creates_parents(tmp_path: Path):
    target = tmp_path / "deeply" / "nested" / "out.json"
    atomic_write_json(target, {"ok": True})
    assert target.exists()


def test_atomic_write_overwrites(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 2}


def test_atomic_write_no_temp_files_left(tmp_path: Path):
    target = tmp_path / "out.json"
    atomic_write_json(target, {"v": 1})
    leftover = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftover == []


def test_atomic_write_preserves_original_on_failure(tmp_path: Path, monkeypatch):
    """If serialisation succeeds but os.replace fails, original is preserved."""
    target = tmp_path / "out.json"
    atomic_write_json(target, {"v": "original"})

    real_replace = os.replace

    def boom(*a, **k):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_json(target, {"v": "new"})

    monkeypatch.setattr(os, "replace", real_replace)
    # original survives
    assert json.loads(target.read_text()) == {"v": "original"}
    # tempfile cleaned up
    leftover = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftover == []
