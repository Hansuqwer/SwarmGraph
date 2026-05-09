from ai_provider_swarm_gateway.cache import SemanticCache


def test_exact_cache_hit(tmp_path):
    cache = SemanticCache(tmp_path / "cache.db")
    cache.set(
        "hello",
        '{"ok": true}',
        provider_id="p1",
        model_id="m1",
    )

    assert cache.get("hello", provider_id="p1", model_id="m1") == '{"ok": true}'


def test_cache_is_scoped_by_provider_and_model(tmp_path):
    cache = SemanticCache(tmp_path / "cache.db")
    cache.set("hello", "p1", provider_id="p1", model_id="m1")

    assert cache.get("hello", provider_id="p2", model_id="m1") is None
    assert cache.get("hello", provider_id="p1", model_id="m2") is None


def test_expired_entry_is_ignored_and_pruned(tmp_path):
    cache = SemanticCache(tmp_path / "cache.db")
    cache.set("hello", "expired", provider_id="p1", model_id="m1", ttl_seconds=-1)

    assert cache.get("hello", provider_id="p1", model_id="m1") is None
    assert cache.prune_expired() == 1


def test_vector_similarity_hit(tmp_path):
    cache = SemanticCache(tmp_path / "cache.db", similarity_threshold=0.9)
    cache.set(
        "first prompt",
        "cached",
        provider_id="p1",
        model_id="m1",
        embedding=[1.0, 0.0, 0.0],
    )

    assert (
        cache.get(
            "different words",
            provider_id="p1",
            model_id="m1",
            embedding=[0.99, 0.01, 0.0],
        )
        == "cached"
    )


def test_vector_similarity_miss(tmp_path):
    cache = SemanticCache(tmp_path / "cache.db", similarity_threshold=0.9)
    cache.set(
        "first prompt",
        "cached",
        provider_id="p1",
        model_id="m1",
        embedding=[1.0, 0.0],
    )

    assert (
        cache.get(
            "different words",
            provider_id="p1",
            model_id="m1",
            embedding=[0.0, 1.0],
        )
        is None
    )


def test_exact_hit_works_without_embedding(tmp_path):
    cache = SemanticCache(tmp_path / "cache.db")
    cache.set("hello", {"text": "ok"}, provider_id="p1", model_id="m1")

    assert cache.get("hello", provider_id="p1", model_id="m1") == '{"text": "ok"}'


def test_cache_is_scoped_by_tenant(tmp_path):
    cache = SemanticCache(tmp_path / "cache.db")
    cache.set("hello", "a", tenant_id="tenant-a", provider_id="p1", model_id="m1")
    cache.set("hello", "b", tenant_id="tenant-b", provider_id="p1", model_id="m1")

    assert cache.get("hello", tenant_id="tenant-a", provider_id="p1", model_id="m1") == "a"
    assert cache.get("hello", tenant_id="tenant-b", provider_id="p1", model_id="m1") == "b"
    assert cache.get("hello", provider_id="p1", model_id="m1") is None


def test_cache_shared_mode_requires_tenant(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_CACHE_SHARED_MODE", "1")
    cache = SemanticCache(tmp_path / "cache.db")

    try:
        cache.get("hello", provider_id="p1", model_id="m1")
    except ValueError as exc:
        assert "tenant_id is required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_cache_migrates_v1_schema(tmp_path):
    import sqlite3

    db_path = tmp_path / "cache.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE cache_entries (
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
            """
            INSERT INTO cache_entries (
                prompt_hash, prompt, response_json, provider_id, model_id, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("x", "hello", "cached", "p1", "m1", 1.0, None),
        )

    SemanticCache(db_path)
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cache_entries)")}
        row = conn.execute("SELECT tenant_id, response_json FROM cache_entries").fetchone()

    assert "tenant_id" in columns
    assert row == ("", "cached")
