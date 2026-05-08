# Research — Pydantic v2 Best Practices (May 2026 Baseline)

> Anchors the **TYPE** finding category used by every sub-agent.

## Mandatory `ConfigDict` patterns

```python
from pydantic import BaseModel, ConfigDict, Field

# Mutable runtime state objects
class State(BaseModel):
    model_config = ConfigDict(
        extra="forbid",                # reject unknown fields on deserialization
        validate_assignment=True,      # validate mutations, not just construction
        use_enum_values=True,          # serialize enums as their values
        revalidate_instances="never",  # set "always" for hot-reloaded configs
    )

# Immutable value objects / config
class Config(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,                   # hashable + raises on mutation attempts
        use_enum_values=True,
        strict=True,                   # disable type coercion (catches "30" vs 30)
    )
```

Source: Pydantic v2 docs, `devtoolbox.dedyn.io/blog/pydantic-complete-guide` (Feb 2026).

## Speed wins (Rust core, May 2026)

| Pattern | Why |
|---|---|
| `model_validate_json(bytes)` instead of `json.loads()` + `model_validate(dict)` | Skips a Python dict hop; entire validation runs in Rust |
| `TypeAdapter(list[Model])` for bulk | Single Rust pass for the whole list |
| `model_dump(mode="json")` for LangGraph state | Emits JSON-safe primitives (datetimes → ISO, UUIDs → str) — required for `BaseCheckpointSaver` round-trip |
| `Annotated[int, Field(ge=0)]` over `int = Field(default=0, ge=0)` | Lets you reuse the constrained type as a function-arg annotation |

## Validators (modern style)

```python
from pydantic import field_validator, model_validator

class M(BaseModel):
    x: int

    @field_validator("x")
    @classmethod
    def _x_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("x must be > 0")
        return v

    @model_validator(mode="after")
    def _cross_field(self) -> "M":
        # invariant checks across multiple fields
        return self
```

`mode="before"` for pre-coercion checks; `mode="after"` for post-construction invariants. **Never** use `@validator` (v1, deprecated since 2.0).

## Discriminated unions (replaces "schema-free `list[dict]`")

```python
from typing import Annotated, Literal, Union
from pydantic import Field

class ShellEntry(BaseModel):
    kind: Literal["shell"]
    command: str

class AgentEntry(BaseModel):
    kind: Literal["agent"]
    output: dict

HistoryEntry = Annotated[Union[ShellEntry, AgentEntry], Field(discriminator="kind")]
```

This is exactly what `ai-coder-hardening-improved/src/ai_coder/workflow/state.py` does (verified at lines 60-100).

## Round-trip checklist for LangGraph state

✅ All fields JSON-serializable (no `Path`, no `datetime` without `mode="json"`, no `bytes`)
✅ `extra="forbid"` so attacker-controlled checkpoint payloads don't smuggle fields
✅ Bounded list/dict fields (memory exhaustion = denial of service)
✅ `model_dump(mode="json")` on write, `model_validate()` on read
✅ Round-trip test: `assert M.model_validate(m.model_dump(mode="json")) == m`

## Common anti-patterns flagged by every TYPE auditor

| Anti-pattern | Severity | Fix |
|---|---|---|
| `model_config = ConfigDict()` (empty) | high | At minimum add `extra="forbid"` |
| `list[dict]` with no schema | high | Use discriminated union |
| `int` for counts without `ge=0` | med | `Field(ge=0)` or `NonNegativeInt` |
| `str` path without validator | high | `field_validator` against `..` and absolute |
| Mutating a field on a `frozen=True` model | critical | Use `model_copy(update={...})` |
| Catching `Exception` then `model_validate` again | med | Only validate at trust boundaries |
