# Research — LangGraph Best Practices (May 2026 Baseline)

> Anchors the **LG** finding category used by every sub-agent.

## Stable APIs as of May 2026

- `langgraph>=0.3.0`, `langgraph-checkpoint>=2.0.0` (the versions pinned in `hive-swarm/pyproject.toml`)
- `langgraph.graph.StateGraph`, `START`, `END`
- `langgraph.types.Send` — fan-out
- `langgraph.types.interrupt` + `Command(resume=...)` — HITL
- `langgraph.checkpoint.base.BaseCheckpointSaver` (sync + async methods, see below)
- `langgraph.checkpoint.{memory,sqlite,postgres}` — production-grade savers

## `BaseCheckpointSaver` — full method surface to override

A custom subclass (e.g. `SwarmRedactingCheckpointer`) **must** override **every** method below, otherwise writes can leak unredacted data through unimplemented async paths:

```
sync:  get_tuple, list, put, put_writes
async: aget_tuple, alist, aput, aput_writes
```

**Coverage trap**: if you only override `put`/`put_writes` but rely on `__getattr__` to proxy `aput`/`aput_writes` to `self.inner`, async callers bypass redaction entirely. The fix used in both `ai-coder-hardening-improved` and `hive-swarm` is to **explicitly implement all 8 methods**.

CI guard recipe (suggested):

```python
def test_redacting_checkpointer_covers_all_abstract_methods():
    abstract = set(BaseCheckpointSaver.__abstractmethods__)
    implemented = {m for m in abstract if SwarmRedactingCheckpointer.__dict__.get(m) is not None}
    assert abstract == implemented, f"Missing redaction overrides: {abstract - implemented}"
```

## `Send()` fan-out — correct usage

```python
def queen_node(state) -> list[Send]:
    return [
        Send("worker_node", AgentState(...).model_dump(mode="json"))
        for _ in range(n_workers)
    ]
```

The targeted node **must** accept the per-Send payload as its sole input — it does **not** see the full graph state. Workers' return dicts are merged back into graph state via the channel reducers.

Source: LangChain forum `forum.langchain.com/t/auto-resuming-challenges-in-langgraph` (Sep 2025) and Swarnendu De's "LangGraph Best Practices" (Sep 2025).

## `interrupt()` + `Command(resume=...)` — HITL contract

```python
from langgraph.types import interrupt, Command

def approval_node(state):
    decision = interrupt({"question": "Approve action X?", "kind": "approval"})
    # control returns here on Command(resume={...})
    return {"approval": decision}

# caller side:
graph.invoke({"foo": 1}, config={"configurable": {"thread_id": "t1"}})
# ... interrupted ...
graph.invoke(Command(resume={"decision": "approve"}), config=same_config)
```

**Hard requirement**: a checkpointer **must** be configured, otherwise resume cannot find the interrupt frame.

**Trap**: if you call `interrupt()` from inside a `@tool` (LangChain tool) without using a graph node wrapper, `Command(resume=...)` cannot route back into tool execution. Use a node wrapper.

## `thread_id` discipline

Every invocation must carry a meaningful `thread_id` in `config["configurable"]`. Recommended pattern:

```python
config = {"configurable": {
    "thread_id": f"tenant-{t}:user-{u}:session-{s}",
    "checkpoint_ns": f"tenant-{t}",
}}
```

Without this, `interrupt()` resume + checkpoint replay both silently break.

## Conditional edges — exhaustiveness rule

```python
builder.add_conditional_edges(
    "router_node",
    route_fn,
    {"a": "node_a", "b": "node_b", END: END},  # MUST cover every possible return
)
```

Auditor recipe: read the routing function's `return` statements, build a set, compare to the dict keys. Any uncovered string is a silent dead-end.

## `dict` vs `BaseModel` graph state

LangGraph supports both:

- `StateGraph(dict)` — what `hive-swarm/swarm/graphs/factory.py` uses; SwarmState is serialized via `to_json_dict()` on every node return.
- `StateGraph(SwarmState)` — would require Pydantic-aware reducers.

The `dict` approach is more portable and is what every guide in 2026 recommends, **provided** every node does `SwarmState.model_validate(state)` on entry (verified pattern in this repo).

## Known footguns observed in the wild (May 2026)

1. **Recursion limits** default to 25; long-running swarms must set `compile(recursion_limit=N)`.
2. **`InMemorySaver` is not durable** — fine for tests, never for prod. Use `PostgresSaver` with `psycopg_pool.ConnectionPool`.
3. **`Send()` payloads must be JSON-serialisable** — dataclasses without `model_dump` fail silently.
4. **`reducer=add_messages` mutates state in-place** — opt out by using `Annotated[list, operator.add]` for typed lists.
5. **Async/sync mixing** — `aput` calling sync `put` deadlocks under `asyncio.run`.
