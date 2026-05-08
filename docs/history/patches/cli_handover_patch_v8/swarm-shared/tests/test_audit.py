"""Tests for swarm_shared.audit — tamper-evidence is the whole product."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from swarm_shared.audit import (
    AuditChain,
    AuditChainBroken,
    AuditRecord,
    GENESIS_PREV_HASH,
    append_jsonl,
    load_jsonl_chain,
    sign_record,
    verify_chain,
    verify_record,
)


SECRET = b"test-hmac-secret-not-real"
ALT_SECRET = b"different-secret"


# ── sign_record / verify_record basics ──────────────────────────────────

def test_sign_then_verify_roundtrip():
    rec = sign_record(
        kind="consensus_result",
        swarm_id="s1",
        sequence=0,
        payload={"action": "do thing", "agreement": 0.9},
        prev_hash=GENESIS_PREV_HASH,
        secret=SECRET,
    )
    assert verify_record(rec, secret=SECRET, expected_prev_hash=GENESIS_PREV_HASH) is True


def test_record_hash_is_64_hex():
    rec = sign_record(
        kind="worker_result",
        swarm_id="s1",
        sequence=0,
        payload={"x": 1},
        prev_hash=GENESIS_PREV_HASH,
        secret=SECRET,
    )
    assert len(rec.record_hash) == 64
    assert len(rec.signature) == 64
    assert all(c in "0123456789abcdef" for c in rec.record_hash)
    assert all(c in "0123456789abcdef" for c in rec.signature)


def test_distinct_payloads_distinct_hashes():
    a = sign_record(kind="worker_result", swarm_id="s1", sequence=0,
                    payload={"x": 1}, prev_hash=GENESIS_PREV_HASH, secret=SECRET)
    b = sign_record(kind="worker_result", swarm_id="s1", sequence=0,
                    payload={"x": 2}, prev_hash=GENESIS_PREV_HASH, secret=SECRET)
    assert a.record_hash != b.record_hash
    assert a.signature != b.signature


def test_same_payload_same_hash_when_timestamp_quantized():
    """Determinism: same logical content → same record_hash (modulo timestamp)."""
    ts = 1234567890.12345
    a = sign_record(kind="worker_result", swarm_id="s1", sequence=0,
                    payload={"x": 1}, prev_hash=GENESIS_PREV_HASH,
                    secret=SECRET, timestamp=ts)
    b = sign_record(kind="worker_result", swarm_id="s1", sequence=0,
                    payload={"x": 1}, prev_hash=GENESIS_PREV_HASH,
                    secret=SECRET, timestamp=ts)
    assert a.record_hash == b.record_hash


# ── verify_record failure modes ─────────────────────────────────────────

def test_verify_wrong_secret_raises():
    rec = sign_record(kind="worker_result", swarm_id="s1", sequence=0,
                      payload={"x": 1}, prev_hash=GENESIS_PREV_HASH, secret=SECRET)
    with pytest.raises(AuditChainBroken, match="signature mismatch"):
        verify_record(rec, secret=ALT_SECRET, expected_prev_hash=GENESIS_PREV_HASH)


def test_verify_wrong_prev_hash_raises():
    rec = sign_record(kind="worker_result", swarm_id="s1", sequence=0,
                      payload={"x": 1}, prev_hash=GENESIS_PREV_HASH, secret=SECRET)
    with pytest.raises(AuditChainBroken, match="chain break"):
        verify_record(rec, secret=SECRET, expected_prev_hash="WRONG")


def test_verify_tampered_payload_raises():
    """Pydantic frozen model — but we simulate tampering by reconstructing
    the JSON, modifying a field, and reparsing."""
    rec = sign_record(kind="worker_result", swarm_id="s1", sequence=0,
                      payload={"x": 1}, prev_hash=GENESIS_PREV_HASH, secret=SECRET)
    raw = rec.model_dump()
    raw["payload"] = {"x": 999}  # tamper
    tampered = AuditRecord.model_validate(raw)
    # Frozen, extra='forbid', so we have to construct via raw → validate.
    # Tampered record carries the OLD record_hash + signature for the OLD payload.
    with pytest.raises(AuditChainBroken, match="record_hash mismatch"):
        verify_record(tampered, secret=SECRET, expected_prev_hash=GENESIS_PREV_HASH)


def test_verify_tampered_signature_raises():
    rec = sign_record(kind="worker_result", swarm_id="s1", sequence=0,
                      payload={"x": 1}, prev_hash=GENESIS_PREV_HASH, secret=SECRET)
    raw = rec.model_dump()
    # Replace signature with a different valid-looking 64-hex string
    raw["signature"] = "f" * 64
    tampered = AuditRecord.model_validate(raw)
    with pytest.raises(AuditChainBroken, match="signature mismatch"):
        verify_record(tampered, secret=SECRET, expected_prev_hash=GENESIS_PREV_HASH)


# ── verify_chain and threat model ───────────────────────────────────────

def _build_chain(n: int, secret=SECRET) -> list[AuditRecord]:
    """Produce a clean chain of n records."""
    chain = AuditChain(swarm_id="s1", secret=secret)
    for i in range(n):
        chain.append(kind="worker_result", payload={"i": i})
    return chain.records


def test_clean_chain_verifies():
    records = _build_chain(5)
    assert verify_chain(records, secret=SECRET) == 5


def test_chain_with_wrong_secret_fails():
    records = _build_chain(3)
    with pytest.raises(AuditChainBroken, match="signature mismatch"):
        verify_chain(records, secret=ALT_SECRET)


def test_chain_deletion_caught():
    """Removing record[1] from a 5-chain breaks verification."""
    records = _build_chain(5)
    tampered = [records[0]] + records[2:]   # delete index 1
    with pytest.raises(AuditChainBroken):
        verify_chain(tampered, secret=SECRET)


def test_chain_insertion_caught():
    """Inserting a fake record breaks the next record's chain link."""
    records = _build_chain(3)
    fake = sign_record(
        kind="worker_result", swarm_id="s1", sequence=1,
        payload={"injected": True}, prev_hash=records[0].record_hash,
        secret=SECRET,
    )
    tampered = [records[0], fake, records[1], records[2]]
    # Sequence break catches it before chain hash even matters
    with pytest.raises(AuditChainBroken):
        verify_chain(tampered, secret=SECRET)


def test_chain_reordering_caught():
    """Swapping records 1 and 2 must fail."""
    records = _build_chain(4)
    reordered = [records[0], records[2], records[1], records[3]]
    with pytest.raises(AuditChainBroken):
        verify_chain(reordered, secret=SECRET)


def test_chain_duplicate_sequence_caught():
    records = _build_chain(3)
    duplicated = [records[0], records[1], records[1], records[2]]
    with pytest.raises(AuditChainBroken, match="sequence break"):
        verify_chain(duplicated, secret=SECRET)


def test_chain_payload_swap_caught():
    """Swapping two records' payloads (preserving order) fails."""
    records = _build_chain(3)
    raw0 = records[0].model_dump()
    raw1 = records[1].model_dump()
    # Swap payloads
    raw0["payload"], raw1["payload"] = raw1["payload"], raw0["payload"]
    tampered = [
        AuditRecord.model_validate(raw0),
        AuditRecord.model_validate(raw1),
        records[2],
    ]
    with pytest.raises(AuditChainBroken):
        verify_chain(tampered, secret=SECRET)


# ── AuditChain stateful helper ──────────────────────────────────────────

def test_audit_chain_increments_sequence():
    chain = AuditChain(swarm_id="s1", secret=SECRET)
    r1 = chain.append(kind="consensus_result", payload={"x": 1})
    r2 = chain.append(kind="approval_decision", payload={"x": 2})
    r3 = chain.append(kind="worker_result", payload={"x": 3})
    assert r1.sequence == 0
    assert r2.sequence == 1
    assert r3.sequence == 2


def test_audit_chain_links_via_prev_hash():
    chain = AuditChain(swarm_id="s1", secret=SECRET)
    r1 = chain.append(kind="worker_result", payload={"x": 1})
    r2 = chain.append(kind="worker_result", payload={"x": 2})
    assert r1.prev_hash == GENESIS_PREV_HASH
    assert r2.prev_hash == r1.record_hash
    assert chain.head_hash == r2.record_hash


def test_audit_chain_self_verifies():
    chain = AuditChain(swarm_id="s1", secret=SECRET)
    for i in range(7):
        chain.append(kind="worker_result", payload={"i": i})
    assert chain.verify() == 7


def test_audit_chain_with_tenant_id():
    chain = AuditChain(swarm_id="s1", secret=SECRET, tenant_id="alice")
    r = chain.append(kind="worker_result", payload={"x": 1})
    assert r.tenant_id == "alice"


# ── JSONL persistence ──────────────────────────────────────────────────

def test_jsonl_round_trip(tmp_path: Path):
    fp = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=fp)
    for i in range(3):
        chain.append(kind="worker_result", payload={"i": i})

    loaded = load_jsonl_chain(fp)
    assert len(loaded) == 3
    assert verify_chain(loaded, secret=SECRET) == 3


def test_jsonl_appends_line_by_line(tmp_path: Path):
    fp = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=fp)
    chain.append(kind="worker_result", payload={"i": 0})
    # One line so far
    assert fp.read_text().count("\n") == 1

    chain.append(kind="worker_result", payload={"i": 1})
    assert fp.read_text().count("\n") == 2


def test_jsonl_load_skips_blank_lines(tmp_path: Path):
    fp = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET)
    chain.append(kind="worker_result", payload={"i": 0})
    chain.append(kind="worker_result", payload={"i": 1})
    raw = "\n".join([
        chain.records[0].model_dump_json(),
        "",
        "  ",
        chain.records[1].model_dump_json(),
        "",
    ])
    fp.write_text(raw)
    loaded = load_jsonl_chain(fp)
    assert len(loaded) == 2


def test_jsonl_load_malformed_raises(tmp_path: Path):
    fp = tmp_path / "bad.jsonl"
    fp.write_text("{not valid json\n")
    with pytest.raises(ValueError, match="malformed"):
        load_jsonl_chain(fp)


def test_jsonl_oversized_record_rejected(tmp_path: Path):
    """Defensive: records > 4KB risk torn appends on POSIX."""
    fp = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=fp)
    big = {"text": "x" * 5000}
    with pytest.raises(ValueError, match="too large"):
        chain.append(kind="worker_result", payload=big)


# ── Tampering on disk ──────────────────────────────────────────────────

def test_disk_tampering_caught_on_reload(tmp_path: Path):
    """Edit a JSONL line on disk, reload, verify_chain must raise."""
    fp = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=fp)
    for i in range(3):
        chain.append(kind="worker_result", payload={"i": i})

    # Tamper with the second line: change i=1 to i=999
    lines = fp.read_text().splitlines()
    record1 = json.loads(lines[1])
    record1["payload"] = {"i": 999}
    lines[1] = json.dumps(record1)
    fp.write_text("\n".join(lines) + "\n")

    loaded = load_jsonl_chain(fp)
    with pytest.raises(AuditChainBroken):
        verify_chain(loaded, secret=SECRET)


def test_disk_truncation_caught_on_reload(tmp_path: Path):
    """Deleting the last record from disk → still verifies (it's a valid
    prefix). But reordering or middle-deletion breaks."""
    fp = tmp_path / "audit.jsonl"
    chain = AuditChain(swarm_id="s1", secret=SECRET, jsonl_path=fp)
    for i in range(5):
        chain.append(kind="worker_result", payload={"i": i})

    # Truncate to first 3 lines (still a valid prefix)
    lines = fp.read_text().splitlines()[:3]
    fp.write_text("\n".join(lines) + "\n")

    loaded = load_jsonl_chain(fp)
    # Prefix still verifies (chain integrity within the prefix is intact)
    assert verify_chain(loaded, secret=SECRET) == 3

    # But middle-deletion: keep records 0, 2, 3, 4 → must fail
    full_lines = []
    chain2 = AuditChain(swarm_id="s2", secret=SECRET)
    for i in range(5):
        chain2.append(kind="worker_result", payload={"i": i})
        full_lines.append(chain2.records[-1].model_dump_json())
    middle_deleted = [full_lines[0], full_lines[2], full_lines[3], full_lines[4]]
    fp.write_text("\n".join(middle_deleted) + "\n")
    loaded = load_jsonl_chain(fp)
    with pytest.raises(AuditChainBroken):
        verify_chain(loaded, secret=SECRET)
