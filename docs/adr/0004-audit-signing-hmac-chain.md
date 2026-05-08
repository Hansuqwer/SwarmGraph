# ADR 0004: Audit Signing With HMAC Chain

Status: Accepted

Decision: Audit records are signed with HMAC-SHA256 and linked with a chained `prev_hash`.

Rationale: stdlib-only tamper evidence for insertion, deletion, reorder, and field tampering.
