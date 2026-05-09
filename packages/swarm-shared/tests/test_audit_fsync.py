from __future__ import annotations

from datetime import UTC, datetime

from swarm_shared.audit import GENESIS_PREV_HASH, append_jsonl, sign_record


def _record():
    return sign_record(
        kind="worker_result",
        swarm_id="s1",
        sequence=0,
        payload={"ok": True},
        prev_hash=GENESIS_PREV_HASH,
        secret=b"not-real",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC).timestamp(),
    )


def test_append_jsonl_fsyncs_when_enabled(monkeypatch, tmp_path):
    calls: list[int] = []
    monkeypatch.setattr("swarm_shared.audit.os.fsync", lambda fd: calls.append(fd))

    append_jsonl(tmp_path / "audit.jsonl", _record(), fsync=True)

    assert calls


def test_append_jsonl_does_not_fsync_by_default(monkeypatch, tmp_path):
    calls: list[int] = []
    monkeypatch.setattr("swarm_shared.audit.os.fsync", lambda fd: calls.append(fd))

    append_jsonl(tmp_path / "audit.jsonl", _record())

    assert calls == []
