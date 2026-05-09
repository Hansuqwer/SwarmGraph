"""Internal helper: audit-record signing wired to SwarmState + SwarmConfig.

Centralises the boilerplate so the three signing nodes (consensus,
approval, worker) don't each duplicate the secret-resolution + path-
substitution logic.

Public API:
  - sign_and_record(state, kind, payload) -> dict | None

Design notes:
  - Returns None (no-op) when audit_signing_enabled=False or kind not in
    audit_kinds — caller can call it unconditionally.
  - Resolves secret from os.environ[config.audit_secret_env]. Missing →
    raises AuditMisconfigured (loud — better than silently signing nothing).
  - Persistent JSONL append is best-effort: file errors are swallowed
    after writing to state.errors. The in-memory chain is the source of
    truth; the JSONL file is durability for ops/forensics.
"""

from __future__ import annotations

import os
from typing import Any

from swarm_shared.audit import (
    GENESIS_PREV_HASH,
    AuditChainBroken,
    AuditKind,
    AuditRecord,
    append_jsonl,
    sign_record,
)


class AuditMisconfigured(RuntimeError):
    """Raised when audit_signing_enabled=True but the secret env var is missing."""


def _resolve_secret(state) -> bytes:
    env_var = state.config.audit_secret_env
    if not env_var:
        raise AuditMisconfigured("audit_signing_enabled=True but config.audit_secret_env is empty")
    secret = os.environ.get(env_var)
    if not secret:
        raise AuditMisconfigured(
            f"audit_signing_enabled=True but env var {env_var!r} is unset; "
            f"set it to a non-empty HMAC secret (>= 32 random bytes recommended)"
        )
    return secret.encode("utf-8")


def sign_and_record(state, kind: AuditKind, payload: dict[str, Any]) -> dict | None:
    """Sign + record an event if audit signing is enabled for this kind.

    Returns the AuditRecord as a dict (for inspection) or None when:
      - audit_signing_enabled=False
      - kind not in audit_kinds

    Caller should call this unconditionally after every signed event;
    the no-op case keeps node code clean.
    """
    if not getattr(state.config, "audit_signing_enabled", False):
        return None
    if kind not in getattr(state.config, "audit_kinds", ()):
        return None

    try:
        secret = _resolve_secret(state)
    except AuditMisconfigured as e:
        # Loud failure: write to errors but don't crash the swarm
        state.add_error(f"audit_signing: {e}")
        if getattr(state.config, "audit_fail_closed", False):
            raise
        return None

    prev_hash = state.audit_chain_head or GENESIS_PREV_HASH
    sequence = state.audit_sequence

    try:
        record = sign_record(
            kind=kind,
            swarm_id=state.swarm_id,
            sequence=sequence,
            payload=payload,
            prev_hash=prev_hash,
            secret=secret,
            tenant_id=os.environ.get("AI_PROVIDER_GATEWAY_TENANT", ""),
        )
    except Exception as e:
        state.add_error(f"audit_signing failed for kind={kind}: {e}")
        if getattr(state.config, "audit_fail_closed", False):
            raise RuntimeError(f"audit_signing failed for kind={kind}: {e}") from e
        return None

    record_dict = record.model_dump(mode="json")
    state.append_audit_record(record_dict)

    # Persistent JSONL flush — best effort
    log_path_str = state.config.resolve_audit_log_path(
        swarm_id=state.swarm_id,
        tenant_id=record.tenant_id,
    )
    if log_path_str:
        from pathlib import Path

        try:
            append_jsonl(Path(log_path_str), record)
        except Exception as e:
            state.add_error(f"audit_jsonl_append failed at {log_path_str}: {e}")

    return record_dict


__all__ = ["sign_and_record", "AuditMisconfigured"]
