# Analysis Assertions — Machine-Checkable Claims

> Every assertion below can be re-tested by checking out the repo at SHA `3ca27bf5be69e751cb457c42028855ddb40d1202` and running the sketched command. If any assertion changes, the corresponding finding in `agents/` and `fix_plan.md` should be re-evaluated.

## Assertions

| # | Assertion | How to verify |
|---|---|---|
| A1 | `hive-swarm/swarm/models/state.py:L43` declares `objective_hash: str = Field(default="")` | `grep -n "objective_hash" swarmMain/hive-swarm/swarm/models/state.py` |
| A2 | `_auto_objective_hash` model_validator computes the hash when blank | `grep -A5 "_auto_objective_hash" swarmMain/hive-swarm/swarm/models/state.py` |
| A3 | All 4 consensus protocols use string-equality vote bucketing (`Counter(v.proposed_action ...)`) | `grep -n "Counter(v.proposed_action" swarmMain/hive-swarm/swarm/models/consensus.py` should return 4 hits at L108, L141, L184, L194 |
| A4 | `bft_consensus` uses `math.ceil(len(votes) * quorum_fraction)` formula | `grep -n "math.ceil" swarmMain/hive-swarm/swarm/models/consensus.py` returns L107 |
| A5 | `_DECOMPOSE_FN["adaptive"] is _hierarchical_decompose` | `grep -A3 "_DECOMPOSE_FN" swarmMain/hive-swarm/swarm/nodes/queen.py` |
| A6 | `worker_node` returns `{"_worker_result": ..., "_agent_id": ...}` | `grep -B1 -A4 "_worker_result" swarmMain/hive-swarm/swarm/nodes/worker.py` returns the return dict |
| A7 | `_redact` only matches `obj.startswith("sk-")` strings | `grep -n 'startswith.*sk-' swarmMain/hive-swarm/swarm/nodes/checkpointing.py` |
| A8 | `SwarmRedactingCheckpointer` implements all 8 BaseCheckpointSaver abstract methods | `grep -nE "^\s*(async )?def (a?get_tuple\|a?list\|a?put\|a?put_writes)" swarmMain/hive-swarm/swarm/nodes/checkpointing.py` returns ≥ 8 hits |
| A9 | `WorkflowState.model_config` has `extra='forbid', validate_assignment=True` | `grep -A3 "model_config = ConfigDict" swarmMain/ai-coder-hardening-improved/src/ai_coder/workflow/state.py` |
| A10 | `MemoLesson._SHELL_METACHAR_PATTERN` matches `[;&\|<>\\\`$!(){}\\n\\r*?^~]` | `grep "SHELL_METACHAR_PATTERN" swarmMain/ai-coder-hardening-improved/src/ai_coder/memory/lesson.py` |
| A11 | `LocalCheckpointStore.save` uses `tempfile.mkstemp` + `os.replace` | `grep -n "tempfile.mkstemp\|os.replace" swarmMain/ai-coder-hardening-improved/src/ai_coder/workflow/checkpoints.py` returns ≥ 1 hit each |
| A12 | `FileCheckpointStore.save` uses `tempfile.mkstemp` + `os.replace` | `grep -n "tempfile.mkstemp\|os.replace" swarmMain/hive-swarm/swarm/nodes/checkpointing.py` returns ≥ 1 hit each |
| A13 | `QuotaTracker._save` uses `Path.write_text` (NOT atomic) | `grep -n "write_text" swarmMain/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py` |
| A14 | `_quota_tracker = QuotaTracker()` is module-level singleton | `grep -n "_quota_tracker = QuotaTracker" swarmMain/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/graph/nodes.py` |
| A15 | `swarm_route_node` writes `__votes__:` JSON into `audit_log` | `grep -n "__votes__" swarmMain/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/graph/nodes.py` |
| A16 | `approval_node` has NO `approval_consumed` guard | `grep -c "approval_consumed" swarmMain/hive-swarm/swarm/nodes/approval.py` returns 0 |
| A17 | `WorkflowState.approval_consumed` field exists in ai-coder | `grep "approval_consumed" swarmMain/ai-coder-hardening-improved/src/ai_coder/workflow/state.py` returns ≥ 1 hit |
| A18 | `pyproject.toml` has no upper bound on `pydantic` | `grep "pydantic" swarmMain/hive-swarm/pyproject.toml` shows `pydantic>=2.7.0` (no `<3`) |
| A19 | `_index` declared as `dict[str, dict[str, ...]] = {}` (NOT PrivateAttr) | `grep -B1 "_index" swarmMain/hive-swarm/swarm/models/memory.py` |
| A20 | `memory_retrieve_node` builds `context_injection` and never writes it to state | `grep -A10 "context_injection" swarmMain/hive-swarm/swarm/nodes/sona.py` |

## Acceptance criteria for fix verification

- A fix is **verified** when the corresponding assertion **inverts** AND a new test in `tests/` covers the new behaviour AND the relevant agent artefact is updated.
- Example: F-29A is verified when A13 changes to "uses `tempfile.mkstemp + os.replace`" AND `tests/test_quota_atomic.py` exists AND `agents/agent_29_providers.md` is updated to "29-CORR1: ✅ FIXED".

## Re-test recipe (no actual code execution required)

```bash
# Clone and check out the audited SHA:
git clone https://github.com/Hansuqwer/PydanticLangraphSwarm.git
cd PydanticLangraphSwarm
git checkout 3ca27bf5be69e751cb457c42028855ddb40d1202

# Run each assertion command above and compare to expected results.
# Any divergence ⇒ re-run the corresponding agent.
```
