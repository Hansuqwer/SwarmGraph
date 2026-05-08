"""Router tests — verifies F-14A word-boundary fix."""
import pytest
from swarm.nodes.router import estimate_complexity


def test_simple_task_low_score():
    score = estimate_complexity("rename a variable")
    assert score < 0.3


def test_complex_task_high_score():
    score = estimate_complexity(
        "implement a distributed authentication system with multi-agent orchestration"
    )
    assert score > 0.5


def test_word_boundary_does_not_match_substring():
    """F-14A: 'build' was previously matching every coding task. Should not now."""
    # 'build' as a word would have been complex_keyword; we removed it.
    # Verify a benign 'build' in a simple task does NOT inflate score.
    benign = estimate_complexity("rename build_dir to output_dir")
    # Should still be fairly low (rename is a simple-keyword)
    assert benign < 0.3


def test_decode_does_not_match_code_keyword():
    """A task containing 'decode' must not match 'code' as a substring (gateway concern;
    tested here as a regression for similar router substring bugs)."""
    # Router's _COMPLEX_PATTERNS does not include 'code', so this is implicitly safe.
    score = estimate_complexity("decode this base64 string")
    assert score < 0.5


def test_empty_task_zero_score():
    assert estimate_complexity("") == 0.0
