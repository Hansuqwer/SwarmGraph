"""Production-grade secret redaction (F-20A, F-W6A).

Replaces the toy ``obj.startswith("sk-")`` matcher in
``hive-swarm/swarm/nodes/checkpointing.py:_redact``.

Patterns covered (May 2026 baseline):
  - OpenAI / Anthropic API keys: ``sk-...`` and ``sk-ant-...``
  - AWS access keys: ``AKIA[0-9A-Z]{16}``
  - Google API keys: ``AIza[0-9A-Za-z_-]{35}``
  - GitHub PATs / OAuth: ``gh[pousr]_...`` and ``github_pat_...``
  - JWTs: ``eyJ...`` (header.payload.signature)
  - Bearer tokens: ``Bearer <token>``
  - Database DSNs with embedded creds: ``postgres://user:pass@host/db``
  - Generic high-entropy long strings (opt-in via ``Redactor(detect_high_entropy=True)``)

Both KEYS and VALUES of dicts are redacted (closes 20-SEC2).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable

# ── Patterns ────────────────────────────────────────────────────────────────
SECRET_PATTERNS: list[re.Pattern[str]] = [
    # OpenAI / Anthropic / generic sk- keys (incl. sk-ant-)
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}\b"),
    # AWS access key
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # AWS secret access key (40 base64-ish chars after typical prefix)
    re.compile(r"(?<![A-Za-z0-9])(?:aws_secret_access_key\s*[:=]\s*)?[A-Za-z0-9/+=]{40}(?![A-Za-z0-9])"),
    # Google API key
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    # GitHub PAT (classic + fine-grained)
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82,}\b"),
    # JWT (header.payload.signature)
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    # Bearer tokens
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{10,}\b", re.IGNORECASE),
    # Database DSNs with embedded user:pass
    re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^:\s]+:[^@\s]+@[^/\s]+(?:/[\w\-]*)?", re.IGNORECASE),
    # Slack tokens
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"),
    # Stripe keys
    re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{24,}\b"),
    # Generic Authorization header value
    re.compile(r"(?<=Authorization:\s)[^\s]+", re.IGNORECASE),
]

REDACTED = "[REDACTED]"


def _shannon_entropy(s: str) -> float:
    """Bits-per-char of a string (rough secret detector)."""
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _looks_like_secret(s: str, *, min_len: int = 20, min_entropy: float = 4.0) -> bool:
    """Heuristic: long high-entropy string with no spaces."""
    if len(s) < min_len:
        return False
    if " " in s or "\n" in s:
        return False
    return _shannon_entropy(s) >= min_entropy


def redact_text(text: str, *, detect_high_entropy: bool = False) -> str:
    """Apply every SECRET_PATTERN, returning text with matches replaced by [REDACTED].

    If ``detect_high_entropy`` is True, also redact tokens that look like high-entropy
    secrets (>=4 bits/char, len >=20, no spaces).
    """
    if not isinstance(text, str):
        return text
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub(REDACTED, out)
    if detect_high_entropy:
        # Conservative: only act on whole-string match (avoid mangling code)
        if _looks_like_secret(out.strip()):
            out = REDACTED
    return out


def redact_obj(obj: Any, *, detect_high_entropy: bool = False) -> Any:
    """Recursively redact dict/list/str. Both KEYS and VALUES are walked (F-20-SEC2)."""
    if isinstance(obj, dict):
        return {
            (redact_text(k, detect_high_entropy=detect_high_entropy) if isinstance(k, str) else k):
            redact_obj(v, detect_high_entropy=detect_high_entropy)
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        cls = type(obj)
        return cls(redact_obj(i, detect_high_entropy=detect_high_entropy) for i in obj)
    if isinstance(obj, str):
        return redact_text(obj, detect_high_entropy=detect_high_entropy)
    return obj


class Redactor:
    """Configurable redactor (lets callers opt into high-entropy detection)."""

    def __init__(
        self,
        *,
        detect_high_entropy: bool = False,
        extra_patterns: Iterable[re.Pattern[str]] | None = None,
    ) -> None:
        self.detect_high_entropy = detect_high_entropy
        self.patterns: list[re.Pattern[str]] = list(SECRET_PATTERNS)
        if extra_patterns:
            self.patterns.extend(extra_patterns)

    def redact_text(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        out = text
        for pat in self.patterns:
            out = pat.sub(REDACTED, out)
        if self.detect_high_entropy and _looks_like_secret(out.strip()):
            out = REDACTED
        return out

    def redact(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                (self.redact_text(k) if isinstance(k, str) else k): self.redact(v)
                for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            cls = type(obj)
            return cls(self.redact(i) for i in obj)
        if isinstance(obj, str):
            return self.redact_text(obj)
        return obj
