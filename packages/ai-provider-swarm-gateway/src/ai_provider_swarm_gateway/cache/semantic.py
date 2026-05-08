"""SQLite-backed response cache with optional vector similarity lookup."""
from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from swarm_shared.hashing import full_sha256

_DEFAULT_BASE = Path.home() / ".ai_provider_gateway"
DEFAULT_CACHE_PATH = _DEFAULT_BASE / "semantic_cache.db"


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class SemanticCache:
    """Local response cache scoped by provider and model.

    Exact prompt-hash matches are always attempted first. Vector lookup is used
    only when an embedding is provided and stored entries have compatible dims.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        similarity_threshold: float = 0.92,
        vector_scan_limit: int = 500,
    ) -> None:
        if similarity_threshold < -1.0 or similarity_threshold > 1.0:
            raise ValueError("similarity_threshold must be between -1 and 1")
        if vector_scan_limit < 1:
            raise ValueError("vector_scan_limit must be >= 1")
        self.db_path = Path(db_path or DEFAULT_CACHE_PATH)
        self.similarity_threshold = similarity_threshold
        self.vector_scan_limit = vector_scan_limit
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_hash TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    embedding_json TEXT,
                    response_json TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    UNIQUE(prompt_hash, provider_id, model_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_scope "
                "ON cache_entries(provider_id, model_id, expires_at, created_at)"
            )

    def get(
        self,
        prompt: str,
        *,
        provider_id: str,
        model_id: str,
        embedding: list[float] | None = None,
    ) -> str | None:
        now = time.time()
        prompt_hash = full_sha256(prompt)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT response_json FROM cache_entries
                WHERE prompt_hash = ? AND provider_id = ? AND model_id = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                """,
                (prompt_hash, provider_id, model_id, now),
            ).fetchone()
            if row is not None:
                return str(row["response_json"])

            if not embedding:
                return None

            rows = conn.execute(
                """
                SELECT embedding_json, response_json FROM cache_entries
                WHERE provider_id = ? AND model_id = ?
                  AND embedding_json IS NOT NULL
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (provider_id, model_id, now, self.vector_scan_limit),
            ).fetchall()

        for row in rows:
            try:
                stored = json.loads(row["embedding_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(stored, list):
                continue
            stored_vec = [float(value) for value in stored]
            if _cosine_similarity(embedding, stored_vec) >= self.similarity_threshold:
                return str(row["response_json"])
        return None

    def set(
        self,
        prompt: str,
        response_json: str | dict[str, Any],
        *,
        provider_id: str,
        model_id: str,
        embedding: list[float] | None = None,
        ttl_seconds: int | None = 86_400,
    ) -> None:
        now = time.time()
        expires_at = None if ttl_seconds is None else now + ttl_seconds
        if isinstance(response_json, str):
            response_payload = response_json
        else:
            response_payload = json.dumps(response_json, sort_keys=True)
        embedding_json = json.dumps([float(v) for v in embedding]) if embedding else None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO cache_entries (
                    prompt_hash, prompt, embedding_json, response_json,
                    provider_id, model_id, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(prompt_hash, provider_id, model_id) DO UPDATE SET
                    prompt = excluded.prompt,
                    embedding_json = excluded.embedding_json,
                    response_json = excluded.response_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (
                    full_sha256(prompt),
                    prompt,
                    embedding_json,
                    response_payload,
                    provider_id,
                    model_id,
                    now,
                    expires_at,
                ),
            )

    def prune_expired(self) -> int:
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            )
            return int(cur.rowcount)


__all__ = ["DEFAULT_CACHE_PATH", "SemanticCache"]
