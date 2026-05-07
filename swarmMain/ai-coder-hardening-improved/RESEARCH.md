# Comprehensive Research: Pydantic v2 & LangGraph

## Pydantic v2 — Key Concepts

### Core Architecture
- **BaseModel**: Foundation for all typed data structures. Fields declared with Python type hints.
- **model_config = ConfigDict(...)**: Replaces the inner `Config` class. Supports `extra='forbid'`, `frozen=True`, `from_attributes=True`, `populate_by_name=True`, etc.
- **model_dump() / model_dump_json()**: Replaces `.dict()` / `.json()`. Supports `mode='json'`, `by_alias`, `exclude_none`, `include`.
- **model_validate() / model_validate_json()**: Replaces `parse_obj()` / `parse_raw()`.
- **model_construct()**: Bypass validation (use carefully — only with pre-validated data).

### Validators (v2 style)
```python
@field_validator('field_name', mode='before'|'after'|'wrap')
@classmethod
def validate_fn(cls, v): ...

@model_validator(mode='after')
def cross_field_validate(self) -> Self: ...
```
- `mode='before'`: runs on raw input before type coercion
- `mode='after'`: runs on the coerced, typed value
- `mode='wrap'`: full control — can call or skip inner validation

### Field Constraints
```python
field: str = Field(..., min_length=1, max_length=280, pattern=r'^[A-Z]')
value: float = Field(..., gt=0, lt=100)
```

### Generic Models
```python
class APIResponse(BaseModel, Generic[T]):
    data: T
    success: bool
```

### Discriminated Unions
```python
class Event(BaseModel):
    kind: Literal["payment"]
    method: Union[CreditCard, BankTransfer] = Field(discriminator="type")
```

### Serialization Control
- `model_dump(mode='json')` → JSON-safe dict (datetimes as strings, enums as values)
- `Field(exclude=True)` → omit from serialization
- `Field(serialization_alias='camelCase')` → custom JSON keys

---

## LangGraph — Key Concepts

### Core Primitives
1. **State**: A `TypedDict` or Pydantic `BaseModel` — the shared memory of the graph
2. **Nodes**: Pure Python functions `(state) -> dict` — return partial state updates
3. **Edges**: Control flow — unconditional (`add_edge`) or conditional (`add_conditional_edges`)
4. **Graph**: `StateGraph(StateSchema)` → `.compile(checkpointer=...)`

### State Reducers
```python
from typing import Annotated
from langgraph.graph import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # appends, not overwrites
```

### Human-in-the-Loop (Interrupt)
```python
from langgraph.types import interrupt

def await_approval(state):
    payload = interrupt({"command": state["command"]})
    # execution pauses here; resumes on Command(resume={...})
    decision = payload["decision"]
    ...
```

### Checkpointers (Persistence)
```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

graph = builder.compile(checkpointer=InMemorySaver())
graph.invoke(input, config={"configurable": {"thread_id": "t1"}})
```

### Conditional Routing
```python
builder.add_conditional_edges("node_a", route_fn, {
    "path_x": "node_x",
    "path_y": "node_y",
})
```

### Multi-Agent Patterns
- **Supervisor**: One router node selects which agent runs
- **Parallel (map-reduce)**: Deferred nodes + fan-out/fan-in
- **Consensus**: Multiple agents vote before proceeding

### Production Features (LangGraph 1.0)
- Node caching for performance
- Deferred nodes for map-reduce workflows
- Pre/post hooks for observability
- `Command` object for cross-node state updates
- `InjectedState` for tool-level state access

---

## How This Repo Uses Both

| Feature | Usage in `ai-coder-hardening` |
|---|---|
| `BaseModel` (Pydantic) | `WorkflowState`, `MemoLesson`, `TokenUsage`, `PatchOutput`, agent outputs |
| `field_validator` | `MemoLesson` — glob safety, shell metachar checks, URL prohibition |
| `model_dump(mode='json')` | Checkpoint serialization, artifact saving |
| `model_validate()` | Deserializing checkpoints back from JSON |
| `Literal` types | `WorkflowStatus`, `FailureCause` — exhaustive status enums |
| `Field(default_factory=...)` | `history`, `errors`, `model_errors` lists |
| LangGraph `StateGraph` | `build_graph()` in `langgraph_runtime.py` |
| LangGraph `interrupt()` | `await_approval` node — human-in-the-loop approval gate |
| LangGraph `Command(resume=...)` | Resume after approval decision |
| LangGraph `BaseCheckpointSaver` | `RedactingCheckpointer` wraps inner saver with secret redaction |
| LangGraph `InMemorySaver` / `SqliteSaver` / `PostgresSaver` | Multi-backend checkpoint support |
