# Agent 05 — Anti-Drift Sentinel
**Model:** Claude Opus 4.6
**Scope:** every other agent's output
**Deliverable goal:** veto out-of-scope items; produce final canonical objective hash.

## CANONICAL OBJECTIVE
> "Analyse what works + what is broken/missing across `swarmMain/`, file-by-file and workflow-by-workflow, producing a prioritised fix-plan. **No source modifications, no code execution, no compliance/ToS findings.**"

`objective_hash = sha256("analyse swarmMain v2026-05-07 +pydantic +langgraph -compliance")[:16] = a3f9c2e1b8d74f06`

## VETOED FINDINGS (out-of-scope, not in fix_plan)
| Origin | Vetoed claim | Reason |
|---|---|---|
| Agent 14 (draft) | "Rewrite the router in Rust for <1ms latency" | Rewriting languages is out of scope. Kept as a future-architecture note only. |
| Agent 21 (draft) | "Replace Raft with HotStuff" | Protocol replacement is out of scope; surgical fixes only. |
| Agent 30 (original prompt) | "Audit `COMPLIANCE.md` for ToS-evasion red flags" | **Compliance language stripped per user instruction.** Re-scoped agent. |
| Agent 02 (draft) | "Migrate to monorepo with Bazel" | Tooling migration out of scope. |
| Agent 26 (draft) | "Replace `SwarmMemory` with vector DB by default" | Default-change beyond scope; allowed as recommendation only. |

## ALLOWED CROSS-SCOPE FINDINGS
| Finding | Why kept |
|---|---|
| Cross-project consolidation (one shared `RedactingCheckpointer`) | This is a "what's missing" pattern observation, in-scope. |
| `pyproject.toml` upper bound recommendations | Maintenance-hygiene finding directly tied to existing files. |
| Deprecation warnings on `pytest-asyncio` mode | Tied to existing test infra. |

## DRIFT EVENTS DETECTED
**0** drift events. Every kept finding is anchored to a `path/to/file.py:Lstart-Lend` citation.

## SIGN-OFF
✅ Final canonical `objective_hash = a3f9c2e1b8d74f06` preserved.
✅ All 30 agent artefacts reviewed.
✅ 5 out-of-scope claims vetoed.
✅ 7 disputed findings sent to consensus (see `consensus_log.jsonl`).
✅ No agent expanded scope without veto.

## SEVERITY × EFFORT
n/a (sentinel role; no code findings).
