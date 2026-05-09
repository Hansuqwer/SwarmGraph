"""Hashing helpers (F-06C, W6 consolidation)."""

from __future__ import annotations

import hashlib


def stable_hash(text: str, length: int = 16) -> str:
    """SHA-256 hex prefix.

    NOTE: 16-char prefix = 64-bit collision space.
    Do NOT use for content-addressing where collision resistance matters
    (e.g., dedup of arbitrary user blobs at scale > 2^32).
    Suitable for: objective_hash, output_hash, task_hash, entry_hash.
    """
    if not isinstance(text, str):
        raise TypeError(f"stable_hash expects str, got {type(text).__name__}")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def full_sha256(text: str) -> str:
    """Full 64-char SHA-256 hex digest. For content-addressable storage."""
    if not isinstance(text, str):
        raise TypeError(f"full_sha256 expects str, got {type(text).__name__}")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
