from swarm.llm.embeddings import SentenceTransformerEmbedder


class _FakeVector:
    def tolist(self):
        return [0.1, 0.2, 0.3]


class _FakeModel:
    def encode(self, text):
        assert text == "hello"
        return _FakeVector()


class _BadModel:
    def encode(self, text):
        raise RuntimeError("boom")


def test_sentence_transformer_embedder_uses_injected_model():
    embedder = SentenceTransformerEmbedder(model=_FakeModel())

    assert embedder.embed("hello") == [0.1, 0.2, 0.3]


def test_sentence_transformer_embedder_empty_text_returns_empty():
    embedder = SentenceTransformerEmbedder(model=_FakeModel())

    assert embedder.embed("") == []


def test_sentence_transformer_embedder_model_failure_returns_empty():
    embedder = SentenceTransformerEmbedder(model=_BadModel())

    assert embedder.embed("hello") == []
