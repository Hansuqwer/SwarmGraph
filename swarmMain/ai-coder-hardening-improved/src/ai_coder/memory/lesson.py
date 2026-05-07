"""Typed memory lesson schema and retrieval contract — hardened edition.

Improvements over original:
  - Expanded shell metachar denylist covers bash history expansion (!),
    subshell grouping ( ), brace expansion { }, and newlines (C4).
  - Added a comprehensive test helper `unsafe_summary_examples()` for CI.
  - MemoLesson is frozen (immutable after creation) to prevent post-storage mutation.
  - file_glob validates against a safe character allowlist in addition to
    the existing relative-path and traversal checks.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Shell metacharacter patterns (C4 — expanded denylist)
# ---------------------------------------------------------------------------

# Original pattern: r"[;&|<>\\`$]"
# Added: ! (history expansion), ( ) (subshell), { } (brace expansion),
#        \n \r (newline injection), * ? (glob injection into shell context),
#        ^ (negation in some shells), ~ (tilde expansion)
_SHELL_METACHAR_PATTERN: re.Pattern[str] = re.compile(
    r'[;&|<>\\`$!()\{\}\n\r*?^~]'
)

_URL_PATTERN: re.Pattern[str] = re.compile(r'https?://', re.IGNORECASE)

# Only allow safe characters in file_glob: alphanumerics, path separators,
# dots, underscores, hyphens, brackets (for glob classes), and *.
_SAFE_GLOB_PATTERN: re.Pattern[str] = re.compile(
    r'^[a-zA-Z0-9_./*\-\[\]{}?]+$'
)


# ---------------------------------------------------------------------------
# MemoLesson model
# ---------------------------------------------------------------------------

class MemoLesson(BaseModel):
    """A validated lesson learned from a successful review run.

    The summary field is constrained to prevent injection of shell commands,
    URLs, or arbitrarily long text. Lessons are retrieved by exact key match
    on (rule_kind, file_glob), not by semantic similarity.

    The model is frozen (immutable) after creation to prevent post-storage
    mutation of validated data.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,  # immutable after construction
    )

    rule_kind: Literal[
        "test_runner",
        "patch_validator",
        "security_guard",
        "style_guide",
    ]
    file_glob: str = Field(..., min_length=1, max_length=128)
    summary: str = Field(..., min_length=1, max_length=280)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    review_passed: bool = Field(default=True)

    # ---------------------------------------------------------------------------
    # Validators
    # ---------------------------------------------------------------------------

    @field_validator("file_glob")
    @classmethod
    def _file_glob_must_be_valid_glob(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("file_glob must be relative, not absolute")
        if ".." in v.split("/"):
            raise ValueError("file_glob must not contain parent traversal (..)")
        # C4 hardening: only safe glob characters
        if not _SAFE_GLOB_PATTERN.match(v):
            raise ValueError(
                "file_glob contains invalid characters; "
                "only alphanumerics, path separators, dots, hyphens, "
                "underscores, brackets, *, and ? are allowed"
            )
        return v

    @field_validator("summary")
    @classmethod
    def _summary_must_not_contain_shell_or_urls(cls, v: str) -> str:
        # C4: expanded shell metachar check
        if _SHELL_METACHAR_PATTERN.search(v):
            raise ValueError(
                "summary must not contain shell metacharacters "
                "(; & | < > \\ ` $ ! ( ) { } newlines * ? ^ ~)"
            )
        if _URL_PATTERN.search(v):
            raise ValueError("summary must not contain URLs")
        return v

    @field_validator("review_passed")
    @classmethod
    def _review_must_have_passed(cls, v: bool) -> bool:
        if not v:
            raise ValueError("only lessons from approved runs may be stored")
        return v

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def key(self) -> tuple[str, str]:
        """Exact lookup key: (rule_kind, file_glob)."""
        return (self.rule_kind, self.file_glob)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def unsafe_summary_examples() -> list[str]:
    """Return examples that should all fail MemoLesson.summary validation.

    Used in CI / unit tests to verify the denylist is effective.
    """
    return [
        # Original denylist
        "run; rm -rf /",
        "echo hello && exit",
        "cmd | tee output",
        "echo `whoami`",
        "echo $SECRET",
        # C4 additions
        "!!",                          # history expansion
        "echo (subshell)",             # subshell
        "echo {a,b}",                  # brace expansion
        "line1\nline2",                # newline injection
        "line1\r\nline2",              # CRLF injection
        "ls *",                        # glob in shell context
        "https://evil.com/payload",    # URL
        "http://example.com",          # URL (http)
    ]
