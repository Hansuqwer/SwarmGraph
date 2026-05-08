# Agent 28 — Lesson Memory Auditor (ai-coder)
**Model:** Claude Sonnet 4.6
**Scope:** `ai-coder-hardening-improved/src/ai_coder/memory/lesson.py`

## PURPOSE
`MemoLesson` validators, security regexes, summary length bounds, URL prohibition coverage. **Cross-ref C4** (already mostly covered in `agent_12_memory_models.md`).

## PUBLIC SURFACE (verified)
- `_SHELL_METACHAR_PATTERN: re.Pattern`
- `_URL_PATTERN: re.Pattern`
- `_SAFE_GLOB_PATTERN: re.Pattern`
- `class MemoLesson(BaseModel)` with `extra='forbid', frozen=True`
- `MemoLesson.key() -> tuple[str, str]`
- `unsafe_summary_examples() -> list[str]` — CI helper

## WHAT WORKS ✅
- **C4 confirmed fixed**: `_SHELL_METACHAR_PATTERN` covers `; & | < > \\ \` $ ! ( ) { } \n \r * ? ^ ~` (`lesson.py:L26-L29`) ✅.
- Custom `_SAFE_GLOB_PATTERN` allowlist (`lesson.py:L36-L39`) ✅ — reverses the denylist approach for `file_glob`.
- `frozen=True` makes lessons immutable post-validation ✅ (`lesson.py:L60`).
- `_review_must_have_passed` enforces "only approved runs" (`lesson.py:L99-L103`) ✅.
- `unsafe_summary_examples()` ships a 13-item denylist verification dataset (`lesson.py:L113-L130`) ✅ — strong test posture.
- `created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))` — UTC, no naive dates ✅.

## WHAT'S BROKEN 🔴

### 28-SEC1 (med) — Shell metachar regex misses `=` and `\\` (single backslash inside brackets)
`lesson.py:L27-L29`:
```python
_SHELL_METACHAR_PATTERN = re.compile(r'[;&|<>\\`$!(){}\n\r*?^~]')
```
- `=` is the bash variable assignment / command substitution character. `FOO=bar` in summary is a config string, but `$()` is already covered.
- The regex source `r'[...\\...]'` correctly matches a single backslash ✅ (because `\\` in raw string = literal `\\`, and inside char class `\\` = single `\`).
- Missing: `\t` (tab), `\v` (vertical tab) — less commonly exploited but useful in command injection contexts.
- Missing: `:` (used in `${PATH}:something` constructs).
- Missing: `[` and `]` (bash glob — but allowed in `_SAFE_GLOB_PATTERN`, so context matters; in `summary` they should probably be denied).

### 28-CORR1 (med) — `_URL_PATTERN` matches only `http://` and `https://`
`lesson.py:L32`: `re.compile(r'https?://', re.IGNORECASE)`. Misses:
- `ftp://`
- `file://`
- `git://`
- `data:` URIs (e.g. `data:text/html;base64,...`)
- Bare domains (`evil.com`, `192.168.1.1`)

For a strict "no URLs in lessons" policy, expand the regex.

### 28-CORR2 (low) — `MemoLesson.key() -> tuple[str, str]` returns `(rule_kind, file_glob)` but the docstring says "exact lookup key"
`lesson.py:L107-L109`. Two lessons with the same `(rule_kind, file_glob)` but different summaries would collide on this key. The docstring doesn't address collision policy. Either:
- Include `summary_hash` in key, OR
- Document "last-write-wins" semantics.

### 28-T1 (low) — `_SAFE_GLOB_PATTERN` allows `?` but glob `?` is a wildcard
`lesson.py:L38-L39`: pattern allows `?`. In glob syntax `?` matches one character. That's expected. But in regex (which is **not** what's evaluated here), `?` means optional. Just confirming intent.

### 28-T2 (low) — `summary max_length=280` — see Agent 12 finding 12-CORR5
Tweet-length convention without rationale. Document.

### 28-OBS1 (low) — `unsafe_summary_examples()` is a dev helper but exported (no underscore prefix)
Documentation should clarify it's intended for tests, not public consumption.

## WHAT'S MISSING 🟡
- No `safe_summary_examples()` companion (positive test cases).
- No length / glob fuzzer (Hypothesis strategy).
- No tag / metadata field.
- No "lesson source" provenance (which agent / run produced it?).
- No `MemoLesson.matches(rule_kind, file_path) -> bool` helper to actually use lessons.

## FIX RECOMMENDATION
```python
# lesson.py — diff
_SHELL_METACHAR_PATTERN: re.Pattern[str] = re.compile(
    r'[;&|<>\\`$!(){}\n\r\t\v*?^~=:\[\]]'   # added \t \v = : [ ]
)

_URL_PATTERN: re.Pattern[str] = re.compile(
    r'(?:https?|ftp|file|git|data):',
    re.IGNORECASE,
)

def safe_summary_examples() -> list[str]:
    """Lessons that should pass validation."""
    return [
        "Always use Annotated for Pydantic constraints",
        "Prefer model_validate_json over manual json.loads",
        "Run pytest with --strict-markers",
    ]
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 28-SEC1 missing chars in metachar | med | 5m |
| 28-CORR1 URL pattern coverage | med | 5m |
| 28-CORR2 key collision policy | low | 5m |
| 28-T2 280-char rationale | low | 5m |
| Missing safe examples | low | 10m |
| Missing matches() helper | high | 30m |

**Final verdict on C4:** ✅ The original gap (missing `! ( ) { } \n \r`) is fully addressed. New minor gaps identified above are incremental improvements only.
