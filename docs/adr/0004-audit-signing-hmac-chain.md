# ADR 0004: Audit Signing With HMAC Chain

Status: Accepted

## Context

SwarmGraph targets workflows where operators need tamper evidence for consensus,
approval, worker, and streaming HITL decisions. Logs must be verifiable offline
without trusting the original process.

## Decision

Audit records are signed with HMAC-SHA256 and linked with a chained `prev_hash`.
Verification checks record hashes, signatures, sequence continuity, and optional
head/count pins.

## Consequences

Insertion, deletion, reorder, and field tampering are detected with stdlib crypto.
The HMAC secret remains a critical trust root; compromise of the secret requires
rotation and incident review. Very large payloads should be stored externally with
hashes or URIs in the audit record.

## Alternatives Considered

Asymmetric signatures were deferred to keep the primitive lightweight and easy to
run in local/stub mode. Plain JSONL logs were rejected because they cannot prove
chain integrity.
