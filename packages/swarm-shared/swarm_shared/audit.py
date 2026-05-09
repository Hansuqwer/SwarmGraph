"""Tamper-evident audit log primitives (HMAC-SHA256 + hash chain).

Three primitives:
  - AuditRecord: a frozen Pydantic model carrying canonical fields +
    `prev_hash`, `record_hash`, and `signature`.
  - sign_record(record_dict, *, secret, prev_hash) → AuditRecord
  - verify_record(record, *, secret, prev_hash) → True | raise AuditChainBroken

  Plus two convenience functions for log-level operations:
  - verify_chain(records: Iterable[AuditRecord], *, secret) → None | raise
  - load_jsonl_chain(path) → list[AuditRecord]

Threat model (what this DOES protect against):
  - Insertion of a fake record into the middle of a log
  - Deletion of any record
  - Reordering of records
  - Tampering with any field of any record after signing

Threat model (what this does NOT protect against):
  - Compromise of the HMAC secret (signs / verifies under attacker control)
  - Wholesale log replacement with a different attacker-signed log
    (mitigation: pin the secret rotation timestamp + audit the secret rotation)
  - Side-channel leakage (timestamps, sizes) — out of scope
  - Replay across logs (each log starts with a fresh `prev_hash="GENESIS"`,
    so cross-log replay is detectable but only if you compare both)

Why HMAC + chain rather than just HMAC:
  - HMAC alone catches per-record tampering but not insertion/reordering.
  - Chained `prev_hash` makes the i-th record's signature transitively
    depend on every earlier record. Inserting one breaks all subsequent.
  - Stdlib only — no GPG keyring, no x509 — keeps deployment friction low.

Canonical serialization:
  Records are serialized via `model_dump_json(sort_keys=True)` so the
  signature is deterministic across machines / Python versions. Floats
  serialize as JSON numbers — be aware that adding a float field with
  insufficient precision could cause cross-version drift; always
  pre-quantize floats before assignment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field

# Genesis sentinel — every chain starts with this prev_hash
GENESIS_PREV_HASH = "GENESIS"

AuditKind = Literal[
    "consensus_result",
    "approval_decision",
    "worker_result",
    "stream_hitl_decision",
    "swarm_init",
    "swarm_complete",
]


class AuditChainBroken(ValueError):
    """Raised when a chain hash mismatch or signature mismatch is detected."""


class AuditRecord(BaseModel):
    """One signed entry in an audit chain.

    Fields:
      - kind:        what kind of event this is (Literal — type-checked)
      - swarm_id:    the swarm this record belongs to
      - tenant_id:   optional tenant scope (multi-tenant deployments)
      - sequence:    monotonic counter within the swarm (0-indexed)
      - timestamp:   wall-clock float (informational; not used in signature beyond inclusion)
      - payload:     the actual event data (canonicalised to dict before sign)
      - prev_hash:   record_hash of the previous record (or "GENESIS" for first)
      - record_hash: SHA-256 of the canonical payload + prev_hash + sequence
      - signature:   HMAC-SHA256(secret, record_hash)

    Frozen + extra='forbid' for the standard discipline.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: AuditKind
    swarm_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str = Field(default="", max_length=64)
    sequence: int = Field(..., ge=0)
    timestamp: float = Field(default_factory=time.time)
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = Field(..., min_length=1)
    record_hash: str = Field(..., min_length=64, max_length=64)  # 64 hex = SHA-256
    signature: str = Field(..., min_length=64, max_length=64)  # 64 hex = HMAC-SHA256

    def to_jsonl_line(self) -> str:
        """Serialize to a single JSON line (for append to .jsonl)."""
        return self.model_dump_json() + "\n"


# ── Canonicalisation ─────────────────────────────────────────────────────


def _canonical_payload(payload: Any) -> str:
    """Deterministic JSON of an arbitrary payload.

    `sort_keys=True` makes ordering platform-independent; `default=str`
    coerces non-JSON-native objects (datetimes, paths) to strings rather
    than raising — defensive against future field additions.
    """
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _compute_record_hash(
    *,
    kind: str,
    swarm_id: str,
    tenant_id: str,
    sequence: int,
    timestamp: float,
    payload: Any,
    prev_hash: str,
) -> str:
    """SHA-256 over the canonical body of a record (excluding signature)."""
    body = "|".join(
        [
            f"kind={kind}",
            f"swarm_id={swarm_id}",
            f"tenant_id={tenant_id}",
            f"sequence={sequence}",
            # Quantize timestamp to milliseconds to avoid float-precision drift
            f"timestamp={int(timestamp * 1000)}",
            f"payload={_canonical_payload(payload)}",
            f"prev_hash={prev_hash}",
        ]
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _compute_signature(record_hash: str, secret: bytes | str) -> str:
    """HMAC-SHA256 of the record_hash under the given secret."""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(secret, record_hash.encode("utf-8"), hashlib.sha256).hexdigest()


# ── Public API ───────────────────────────────────────────────────────────


def sign_record(
    *,
    kind: AuditKind,
    swarm_id: str,
    sequence: int,
    payload: dict[str, Any],
    prev_hash: str,
    secret: bytes | str,
    tenant_id: str = "",
    timestamp: float | None = None,
) -> AuditRecord:
    """Build + sign a new audit record.

    Caller is responsible for tracking `prev_hash` (chain head) and
    `sequence` (monotonic counter). The convenience class `AuditChain`
    below tracks both for you.
    """
    if timestamp is None:
        timestamp = time.time()
    record_hash = _compute_record_hash(
        kind=kind,
        swarm_id=swarm_id,
        tenant_id=tenant_id,
        sequence=sequence,
        timestamp=timestamp,
        payload=payload,
        prev_hash=prev_hash,
    )
    signature = _compute_signature(record_hash, secret)
    return AuditRecord(
        kind=kind,
        swarm_id=swarm_id,
        tenant_id=tenant_id,
        sequence=sequence,
        timestamp=timestamp,
        payload=payload,
        prev_hash=prev_hash,
        record_hash=record_hash,
        signature=signature,
    )


def verify_record(
    record: AuditRecord,
    *,
    secret: bytes | str,
    expected_prev_hash: str,
) -> bool:
    """Verify a single record's hash + signature + chain link.

    Raises AuditChainBroken with a precise reason on mismatch.
    Returns True on success (so callers can write `assert verify_record(...)`).
    """
    # 1. Chain link
    if record.prev_hash != expected_prev_hash:
        raise AuditChainBroken(
            f"chain break at sequence={record.sequence}: "
            f"prev_hash={record.prev_hash!r} != expected={expected_prev_hash!r}"
        )

    # 2. Recompute record hash
    expected_hash = _compute_record_hash(
        kind=record.kind,
        swarm_id=record.swarm_id,
        tenant_id=record.tenant_id,
        sequence=record.sequence,
        timestamp=record.timestamp,
        payload=record.payload,
        prev_hash=record.prev_hash,
    )
    if not hmac.compare_digest(expected_hash, record.record_hash):
        raise AuditChainBroken(
            f"record_hash mismatch at sequence={record.sequence}: "
            f"stored={record.record_hash[:16]}... "
            f"computed={expected_hash[:16]}... — record was tampered with"
        )

    # 3. Verify signature
    expected_sig = _compute_signature(record.record_hash, secret)
    if not hmac.compare_digest(expected_sig, record.signature):
        raise AuditChainBroken(
            f"signature mismatch at sequence={record.sequence}: "
            f"stored={record.signature[:16]}... — wrong secret OR tampered signature"
        )

    return True


def verify_chain(
    records: Iterable[AuditRecord],
    *,
    secret: bytes | str,
    initial_prev_hash: str = GENESIS_PREV_HASH,
    expected_head_hash: str | None = None,
    expected_count: int | None = None,
) -> int:
    """Verify an entire chain of records in order.

    Returns the count of records verified.
    Raises AuditChainBroken on the first failure (no further records checked).
    Also catches:
      - Out-of-order sequence numbers
      - Duplicate sequence numbers

    Optional pins catch valid-prefix truncation or whole-log replacement.
    """
    prev_hash = initial_prev_hash
    expected_sequence = 0
    count = 0
    for record in records:
        if record.sequence != expected_sequence:
            raise AuditChainBroken(
                f"sequence break: expected={expected_sequence}, "
                f"got={record.sequence} — records may have been deleted, "
                f"reordered, or duplicated"
            )
        verify_record(record, secret=secret, expected_prev_hash=prev_hash)
        prev_hash = record.record_hash
        expected_sequence += 1
        count += 1
    if expected_count is not None and count != expected_count:
        raise AuditChainBroken(f"record count mismatch: expected={expected_count}, got={count}")
    if expected_head_hash is not None and prev_hash != expected_head_hash:
        raise AuditChainBroken(
            f"head hash mismatch: expected={expected_head_hash[:16]}..., got={prev_hash[:16]}..."
        )
    return count


# ── JSONL persistence ────────────────────────────────────────────────────


def append_jsonl(path: Path, record: AuditRecord) -> None:
    """Append a single record to a JSONL file. Atomic per-line append.

    Uses O_APPEND open mode + a single write() call — POSIX guarantees
    single-write atomicity for buffer sizes < PIPE_BUF (typically 4096
    bytes). AuditRecords serialised as JSON typically fit well within
    that bound, but for safety we limit the line length here.
    """
    line = record.to_jsonl_line()
    byte_len = len(line.encode("utf-8"))
    if byte_len > 4000:
        # Defensive: large payloads risk torn appends on POSIX
        raise ValueError(
            f"audit record too large to safely append ({byte_len} bytes); "
            f"reduce payload size or use a different persistence backend"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()


def load_jsonl_chain(path: Path) -> list[AuditRecord]:
    """Load all records from a JSONL audit log.

    Skips blank lines. Raises ValueError on malformed JSON (so the caller
    knows the file is corrupt, not just tampered with).
    """
    records: list[AuditRecord] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(AuditRecord.model_validate_json(line))
            except Exception as e:
                raise ValueError(f"audit log line {lineno} malformed: {e}") from e
    return records


# ── Convenience: stateful chain builder ──────────────────────────────────


class AuditChain:
    """Stateful helper that tracks chain head + sequence for you.

    Usage:
        chain = AuditChain(swarm_id="s1", secret="...", tenant_id="alice",
                           jsonl_path=Path("audit.jsonl"))
        chain.append(kind="consensus_result", payload={"action": "..."})
        chain.append(kind="approval_decision", payload={"decision": "approve"})
        # ... at end:
        chain.verify()   # raises AuditChainBroken if anything's wrong
    """

    def __init__(
        self,
        *,
        swarm_id: str,
        secret: bytes | str,
        tenant_id: str = "",
        jsonl_path: Path | None = None,
        initial_prev_hash: str = GENESIS_PREV_HASH,
    ) -> None:
        self.swarm_id = swarm_id
        self.tenant_id = tenant_id
        self.secret = secret
        self.jsonl_path = jsonl_path
        self._initial_prev_hash = initial_prev_hash
        self._prev_hash = initial_prev_hash
        self._sequence = 0
        self.records: list[AuditRecord] = []

    @property
    def head_hash(self) -> str:
        """The current chain head hash. New records will have prev_hash=this."""
        return self._prev_hash

    @property
    def length(self) -> int:
        return len(self.records)

    def append(self, *, kind: AuditKind, payload: dict[str, Any]) -> AuditRecord:
        """Sign a new record, append to chain (and JSONL if configured)."""
        record = sign_record(
            kind=kind,
            swarm_id=self.swarm_id,
            tenant_id=self.tenant_id,
            sequence=self._sequence,
            payload=payload,
            prev_hash=self._prev_hash,
            secret=self.secret,
        )
        self.records.append(record)
        self._prev_hash = record.record_hash
        self._sequence += 1
        if self.jsonl_path:
            append_jsonl(self.jsonl_path, record)
        return record

    def verify(
        self,
        *,
        expected_head_hash: str | None = None,
        expected_count: int | None = None,
    ) -> int:
        """Verify the in-memory chain. Returns count of records verified."""
        return verify_chain(
            self.records,
            secret=self.secret,
            initial_prev_hash=self._initial_prev_hash,
            expected_head_hash=expected_head_hash,
            expected_count=expected_count,
        )


__all__ = [
    "AuditKind",
    "AuditRecord",
    "AuditChain",
    "AuditChainBroken",
    "GENESIS_PREV_HASH",
    "sign_record",
    "verify_record",
    "verify_chain",
    "append_jsonl",
    "load_jsonl_chain",
]
