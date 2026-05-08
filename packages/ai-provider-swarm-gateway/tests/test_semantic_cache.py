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
