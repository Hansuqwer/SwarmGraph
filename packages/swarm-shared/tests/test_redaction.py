"""Tests for swarm_shared.redaction (F-20A)."""

from swarm_shared.redaction import (
    REDACTED,
    Redactor,
    redact_obj,
    redact_patch,
    redact_text,
)

OPENAI_KEY = "sk-" + "proj-" + "abcdef1234567890ABCDEF12345678"
ANTHROPIC_KEY = "sk-" + "ant-api03-" + "abcdef1234567890ABCDEF12345678"
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB_PAT = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"
SLACK_TOKEN = "xoxb" + "-1234567890-abcdef"
STRIPE_KEY = "sk" + "_live_" + "abcdefghijklmnopqrstuvwx"
GOOGLE_API_KEY = "AI" + "za" + "Sy" + ("A" * 33)


# ── Pattern-by-pattern coverage ─────────────────────────────────────────────
def test_redacts_openai_key():
    assert REDACTED in redact_text(OPENAI_KEY)


def test_redacts_anthropic_key():
    assert REDACTED in redact_text(ANTHROPIC_KEY)


def test_redacts_aws_access_key():
    assert REDACTED in redact_text(AWS_KEY)


def test_redacts_google_api_key():
    assert REDACTED in redact_text(GOOGLE_API_KEY)


def test_redacts_github_pat():
    assert REDACTED in redact_text(GITHUB_PAT)


def test_redacts_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abc123def456"
    assert REDACTED in redact_text(jwt)


def test_redacts_bearer_token():
    assert REDACTED in redact_text("Authorization: Bearer abcdef123456789")


def test_redacts_postgres_dsn():
    dsn = "postgres://admin:supersecret@db.example.com/prod"
    assert "supersecret" not in redact_text(dsn)


def test_redacts_ssn():
    out = redact_text("candidate ssn 123-45-6789")
    assert "123-45-6789" not in out
    assert REDACTED in out


def test_redacts_credit_card_like_number():
    out = redact_text("card 4111 1111 1111 1111")
    assert "4111" not in out
    assert REDACTED in out


def test_redacts_slack_token():
    assert REDACTED in redact_text(SLACK_TOKEN)


def test_redacts_stripe_key():
    assert REDACTED in redact_text(STRIPE_KEY)


# ── Negative cases (must NOT redact) ───────────────────────────────────────
def test_does_not_redact_short_string():
    assert redact_text("hello") == "hello"


def test_does_not_redact_normal_code():
    code = "def add(a, b): return a + b"
    assert redact_text(code) == code


def test_does_not_redact_empty_string():
    assert redact_text("") == ""


def test_does_not_alter_non_str():
    assert redact_text(42) == 42  # type: ignore[arg-type]
    assert redact_text(None) is None  # type: ignore[arg-type]


# ── redact_obj walks dict KEYS and VALUES (F-20-SEC2) ──────────────────────
def test_redact_obj_redacts_dict_value():
    out = redact_obj({"key": OPENAI_KEY})
    assert out["key"] == REDACTED


def test_redact_obj_redacts_dict_key():
    """Dict keys must also be redacted (the F-20-SEC2 fix)."""
    out = redact_obj({OPENAI_KEY: "value"})
    assert REDACTED in out
    assert "value" in out.values()


def test_redact_obj_walks_nested_lists():
    out = redact_obj([{"token": GITHUB_PAT}])
    assert out[0]["token"] == REDACTED


def test_redact_obj_walks_deep_nesting():
    nested = {"a": {"b": {"c": ["sk-" + "ant-api03-" + "abcdefghijklmnopqrstuv"]}}}
    out = redact_obj(nested)
    assert out["a"]["b"]["c"][0] == REDACTED


# ── Redactor class with high-entropy detection ─────────────────────────────
def test_redactor_high_entropy_detects_long_random():
    r = Redactor(detect_high_entropy=True)
    secret = "abc123XYZ_qrs789TUV456lmn-def-ghi-789"  # gitleaks:allow
    out = r.redact_text(secret)
    assert out == REDACTED


def test_redactor_high_entropy_off_by_default():
    r = Redactor()  # detect_high_entropy=False
    out = r.redact_text("abc123XYZ_qrs789TUV456lmn-def-ghi-789")
    # No pattern matches; high-entropy off → preserved
    assert out == "abc123XYZ_qrs789TUV456lmn-def-ghi-789"


def test_redactor_redaction_applies_to_all_patterns():
    """All built-in patterns trigger via the Redactor instance too."""
    r = Redactor()
    text = ("sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz12") + " and " + AWS_KEY
    out = r.redact_text(text)
    assert "sk-proj" not in out
    assert "AKIA" not in out


# ── Idempotence ─────────────────────────────────────────────────────────────
def test_redact_text_idempotent():
    once = redact_text("Bearer abcdefghijklmnop")
    twice = redact_text(once)
    assert once == twice


def test_redact_patch_preserves_headers_and_redacts_line_bodies():
    patch = (
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-API_KEY = 'sk-oldoldoldoldoldoldoldoldoldold'\n"
        "+API_KEY = 'sk-newnewnewnewnewnewnewnewnewnew'\n"
        " context Bearer abcdefghijklmnopqrstuvwxyz\n"
    )

    redacted = redact_patch(patch)

    assert redacted.startswith("--- a/config.py\n+++ b/config.py\n@@ -1,2 +1,2 @@\n")
    assert "sk-old" not in redacted
    assert "sk-new" not in redacted
    assert "Bearer abc" not in redacted
    assert redacted.count(REDACTED) >= 3
