# Fix Plan — Prioritised, Owner-Tagged

> Each row: **ID** · **Severity (S)** · **Effort (E)** · **File:Lines** · **Owner-agent** · **Blocks**
> Severity: critical / high / med / low. Effort: 1m / 5m / 15m / 30m / 1h / 1d / 1wk.
> "Blocks" = other fixes that depend on this one.

---

## 🔴 P0 — CRITICAL (must-fix before any production deployment)

| ID | S | E | File:Lines | Owner | Description | Blocks |
|---|---|---|---|---|---|---|
| **F-13A** | critical | 1d | `hive-swarm/swarm/graphs/factory.py:L60-L130` + `models/state.py:L66` | A13 + A16 | Add `Annotated[list[WorkerResult], operator.add]` reducer on `SwarmState.worker_results`; OR migrate to `StateGraph(SwarmState)` with Pydantic-aware reducers. Worker returns currently break `extra='forbid'` validation. | F-16A, F-17A |
| **F-16A** | critical | 1h | `hive-swarm/swarm/nodes/worker.py:L100-L103` | A16 | Change worker return from `{"_worker_result": ...}` to `{"worker_results": [result]}` (post F-13A reducer). | F-17A |
| **F-17A** | critical | 1wk | `hive-swarm/swarm/models/consensus.py:L107, L141, L184, L194` | A17 + A11 | Replace string-equality vote bucketing with embedding-cosine clustering (≥ 0.9 similarity = same cluster). Until embeddings are wired, add canonical-form normalization (Python AST hash for code, whitespace-collapse for text). | — |
| **F-19A** | critical | 1h | `hive-swarm/swarm/nodes/approval.py:L26-L62` + `models/state.py` | A19 | Add `approval_consumed: bool = False` field on `SwarmState`; raise `RuntimeError("approval already consumed")` on second entry to `approval_node` for same thread_id. Cross-port from `ai-coder/workflow/state.py:L142`. | F-19B |
| **F-19B** | critical | 30m | `hive-swarm/swarm/nodes/approval.py` | A19 | Define `class ApprovalDecision(BaseModel)` with `extra='forbid', frozen=True` and `decision: Literal["approve","deny"], reviewer_id: str, decision_token: str`. Use `ApprovalDecision.model_validate(raw)` instead of `dict.get`. | — |
| **F-20A** | critical | 1d | `hive-swarm/swarm/nodes/checkpointing.py:L116-L124` | A20 + A12 | Replace toy redaction (`obj.startswith("sk-")`) with regex-based multi-pattern matcher covering: `sk-(ant-)?...`, `AKIA...`, `AIza...`, `gh[pousr]_...`, JWTs (`eyJ...`), `postgres://user:pass@`, `Bearer ...`. Also redact dict KEYS (20-SEC2). | — |
| **F-22A** | critical | 30m | `hive-swarm/swarm/models/consensus.py:L88-L131` | A22 | Reject `len(votes) < 4` for BFT with clear `failure_reason`. Switch threshold formula to `floor(2*n/3) + 1`. Also de-dupe votes by `agent_id` (apply to all 4 protocols). | F-22B |
| **F-22B** | critical | 1d | `hive-swarm/swarm/models/agent.py:L91` + new `swarm/security.py` | A07 + A22 | Add `signature: str | None = None`, `nonce: str = Field(default_factory=secrets.token_hex)`, `round_id: str` to `AgentVote`. Add HMAC helper to sign votes with shared secret. Verify in every consensus protocol. | — |
| **F-25A** | critical | 1d | `hive-swarm/swarm/nodes/queen.py:L74-L80` + new edges in `factory.py` | A25 + A15 | Implement true ring (linear `add_edge` chain) and at least diversified mesh prompts. Either truly implement OR rename topology Literal to `role_set_*` and document the simplification. | F-15B |
| **F-29A** | critical | 1h | `ai-provider-swarm-gateway/.../quota/tracker.py:L33-L37` | A29 | Replace `Path.write_text` with `tempfile.mkstemp + os.replace` atomic pattern (mirror `hive-swarm/swarm/nodes/checkpointing.py:L73-L91`). | — |
| **F-29B** | critical | 1h | `ai-provider-swarm-gateway/.../quota/tracker.py` | A29 | Add `fcntl.flock(LOCK_EX)` around the write OR migrate to SQLite. Two-process race currently loses increments. | — |

## 🟠 P1 — HIGH (significant bugs / missing safety)

| ID | S | E | File:Lines | Owner | Description |
|---|---|---|---|---|---|
| F-04A | high | 1h | `hive-swarm/tests/test_redaction_coverage.py` (new) | A04 | Add CI test asserting `set(BaseCheckpointSaver.__abstractmethods__) <= set(SwarmRedactingCheckpointer.__dict__)`. Future LangGraph 0.4 method additions caught at PR time. |
| F-04B | high | 1d | `hive-swarm/tests/test_property_consensus.py` (new) | A04 | Add Hypothesis-based property tests for all 4 consensus protocols: liveness under random faulty subsets, idempotence, convergence. |
| F-04C | high | 1d | `hive-swarm/tests/test_hitl_resume.py` (new) | A04 | E2E test: drive graph until `interrupt`, resume with real `Command(resume=...)` against a real `InMemorySaver`. Cover both approve/deny/replay-attempt paths. |
| F-04D | high | 1d | `hive-swarm/tests/test_state_roundtrip.py` (new) | A04 | Hypothesis-based round-trip fuzz: `SwarmState.model_validate(s.to_json_dict()) == s`. |
| F-13B | high | 5m | `hive-swarm/swarm/graphs/factory.py:L130` | A13 | Add `recursion_limit=max(25, config.max_iterations * 8)` to `builder.compile`. |
| F-15A | high | 15m | `hive-swarm/swarm/nodes/queen.py:L142-L144` | A15 | Raise loud `RuntimeError` if `Send is None and not send_list`. Currently silently returns dict-list which breaks LangGraph dispatch. |
| F-15B | high | 1d | `hive-swarm/swarm/nodes/queen.py:L80` | A15 | Implement real `_adaptive_decompose` that switches to mesh when prior `consensus_result.agreement_fraction < 0.5`. Or rename `adaptive` → `auto`. |
| F-16B | high | 30m | `hive-swarm/swarm/nodes/worker.py:L131` | A16 | After collecting votes, call `swarm.mark_task_complete(r.task_id, r.output)` for every successful result. |
| F-18A | high | 30m | `hive-swarm/swarm/nodes/judge.py:L62-L67` | A18 | On retry, clear `worker_results = []` and `consensus_result = None` before returning `route_task`. Currently dirty retries see stale state. |
| F-18B | high | 1wk | `hive-swarm/swarm/models/state.py:L143-L155` (`check_drift`) | A18 + A12 | Replace keyword-overlap drift heuristic with embedding-cosine similarity (when `VectorMemoryAdapter` is wired). Until then, document false-positive rate and lower default threshold to 0.25. |
| F-19C | high | 15m | `hive-swarm/swarm/nodes/approval.py:L43` | A19 | Truncate `proposed_action` to 2048 chars in interrupt payload. Add `truncated: bool` flag. |
| F-20B | high | 15m | `hive-swarm/swarm/nodes/checkpointing.py:L94-L101` | A20 | Sort checkpoints by encoded iteration in filename instead of `stat().st_mtime` (NTP-jump safe). |
| F-21A | high | 30m | `hive-swarm/swarm/models/consensus.py:L48-L84` | A21 | Detect split-brain: if `len(queen_votes) > 1`, return `failed=True, failure_reason="Split-brain: N queens"`. Also factor follower disagreement into `agreement_fraction`. |
| F-23A | high | 30m | `hive-swarm/swarm/models/consensus.py:L135-L172` | A23 | Add `confidence_floor=0.05` and `min_voters=3` parameters. Currently 1 high-confidence dissenter beats 4 low-confidence agreers. |
| F-26A | high | 1d | `hive-swarm/swarm/models/memory.py` (new methods) | A26 | Add `SwarmMemory.export_jsonl(path)` / `import_jsonl(path)` for persistence between runs. Currently every swarm starts with empty memory. |
| F-27A | high | 1d | `hive-swarm/swarm/nodes/sona.py:L66-L96` + `models/state.py` | A27 | Add `retrieved_context: list[dict] = Field(max_length=10)` to `SwarmState`; have `memory_retrieve_node` write into it; have `queen_node` read it into `QueenDirective.shared_context`. Closes the SONA loop properly. |
| F-29C | high | 30m | `ai-provider-swarm-gateway/.../graph/nodes.py:L237-L240` | A29 | Replace string-prefixed `audit_log` smuggling with typed `provider_votes: list[ProviderVote]` field on `GatewayState`. |
| F-29D | high | 30m | `ai-provider-swarm-gateway/.../graph/nodes.py:L31` | A29 + A30 | Make `_quota_tracker` injectable rather than module-level singleton; same for `_registry`. |
| F-30A | high | 5m | `ai-provider-swarm-gateway/.../models/state.py` (re-fetch) | A30 | Add `Field(max_length=100_000)` to `GatewayState.user_prompt`. |
| F-30B | high | 1h | `ai-provider-swarm-gateway/.../dashboard/app.py` (re-fetch) | A30 | Re-fetch and audit dashboard for: PII rendering, default-no-auth Streamlit, secret-leakage in CLI flags. |
| F-12A | high | 15m | `hive-swarm/swarm/models/memory.py:L57` | A12 + A26 | Convert `_index` to `PrivateAttr(default_factory=dict)`. Currently it's a class-level mutable default. |

## 🟡 P2 — MEDIUM

| ID | S | E | File:Lines | Owner | Description |
|---|---|---|---|---|---|
| F-03A | med | 1m | `hive-swarm/pyproject.toml` | A03 | Add upper bounds: `pydantic>=2.7,<3`, `langgraph>=0.3,<2`. |
| F-03B | med | 5m | `hive-swarm/pyproject.toml` | A03 | Add `langgraph-checkpoint-sqlite` extra. Code references `SqliteSaver` but the extra isn't declared. |
| F-06A | med | 5m | `hive-swarm/swarm/models/base.py:L18-L23` | A06 | Add `revalidate_instances="never"` (document intent). |
| F-06B | med | 30m | `hive-swarm/swarm/models/base.py:L40-L42` | A06 | Add `monotonic_ts()` for duration math; swap `AgentState.duration_seconds` to use it (avoid wall-clock NTP jumps). |
| F-08A | med | 5m | `hive-swarm/swarm/models/task.py:L51-L54` | A08 | Add real "no self-dependency" model_validator (current `_no_self_dep` only deduplicates). |
| F-09A | med | 10m | `hive-swarm/swarm/models/state.py:L157-L165` | A09 | Reorder `assert_no_drift`: raise BEFORE mutating status (avoids hiding raise behind validator errors). |
| F-09B | high | 1h | `hive-swarm/swarm/models/state.py` (new field) | A09 | Add `schema_version: int = Field(default=1, ge=1)` for future migrations. |
| F-10A | high | 5m | `hive-swarm/swarm/models/config.py:L24` | A10 | Tighten `bft_quorum_fraction: ge=0.667` (PBFT minimum). |
| F-11A | med | 10m | `hive-swarm/swarm/models/consensus.py:L213-L226` | A11 | Document `risk = 1.0 - agreement_fraction` semantics or rename to `disagreement`. Default risk threshold 0.8 means HITL only fires for agreement < 20%. |
| F-11B | high | 1h | `hive-swarm/swarm/models/consensus.py:L21-L41` | A11 | Add `voter_breakdown: dict[str,int]` and `dissenter_ids: list[str]` to `ConsensusResult` for diagnostics. |
| F-13C | med | 15m | `hive-swarm/swarm/graphs/factory.py:L40` + `nodes/router.py:L62` | A13 | Move `_QUEEN_NODE_NAMES` to `models/types.py` (single source of truth). |
| F-14A | med | 30m | `hive-swarm/swarm/nodes/router.py:L17-L52` | A14 | Convert keyword lists to word-boundary regex; remove substring-match false positives (`"build"` matching every coding task). Tune length denominator. |
| F-17B | med | 15m | `hive-swarm/swarm/nodes/consensus.py:L26-L31` | A17 | Add min-voters guard (force `requires_approval=True` for single-voter except Raft). |
| F-17C | med | 5m | `hive-swarm/swarm/nodes/consensus.py:L48` | A17 | Add a history entry on the failure path (currently only success path logs). |
| F-20C | med | 30m | `hive-swarm/swarm/nodes/checkpointing.py` | A20 + W6 | Extract redaction logic into shared `swarm-shared.redaction` package; share with ai-coder. |
| F-22C | med | 5m | `hive-swarm/swarm/models/consensus.py:L88` | A22 | Defensive: assert `quorum_fraction < 1.0` inside `bft_consensus` (config validator already does, but defense in depth). |
| F-24A | med | 15m | `hive-swarm/swarm/models/consensus.py:L194-L201` | A24 | Replace alphabetical tie-break with first-proposer (lowest timestamp) tie-break. |
| F-25B | med | 30m | `hive-swarm/swarm/nodes/queen.py:L41-L48` | A25 | Diversify mesh prompts (currently all 4 workers get the same string). |
| F-26B | med | 30m | `hive-swarm/swarm/models/memory.py:L141-L150` | A26 | `promote_score` should preserve `created_at` instead of resetting via `store()`. |
| F-26C | med | 15m | `hive-swarm/swarm/models/memory.py:L100-L113` | A26 | `search()` should use `_index[namespace]` instead of full-list scan when namespace is set. |
| F-27B | med | 15m | `hive-swarm/swarm/nodes/sona.py` | A27 | Include `swarm_id` in pattern keys to avoid cross-session overwrite. |
| F-28A | med | 5m | `ai-coder/.../memory/lesson.py:L27-L29, L32` | A28 | Expand shell-metachar regex (add `\t \v = : [ ]`) and URL pattern (add `ftp file git data`). |
| F-30C | med | 30m | `ai-provider-swarm-gateway/.../graph/nodes.py:L106-L116` | A30 | Replace substring capability inference with word-boundary regex (`"code"` matches `"decode"`). |
| F-30D | med | 30m | `ai-provider-swarm-gateway/.../graph/nodes.py` (timing decorator) | A30 | Add per-node timing decorator → `state.timing_per_node: dict[str, float]`. |

## 🟢 P3 — LOW (polish, doc drift, dead code)

| ID | S | E | File:Lines | Owner | Description |
|---|---|---|---|---|---|
| F-01A | low | 1h | `hive-swarm/HIVE_LEADER_SYNTHESIS.md` | A01 | Soften "production-ready" claim; add Known Limitations section linking to this fix plan. |
| F-01B | low | 10m | `hive-swarm/swarm/models/memory.py:L141` | A01 | Rename `promote_score` doc reference EWC++ → "score-promotion (EWC-inspired)". |
| F-02A | low | 1m | `hive-swarm/swarm/nodes/queen.py:L9` | A02 | Remove unused `import secrets`. |
| F-06C | low | 10m | `hive-swarm/swarm/models/base.py:L36` | A06 | Add docstring caveat to `stable_hash`: "16-char prefix = 64-bit collision space; do not use for content-addressing." |
| F-07A | low | 5m | `hive-swarm/swarm/models/agent.py:L146-L149` | A07 | `_compute_output_hash` should ALWAYS recompute, not trust caller-provided hash. |
| F-08B | low | 5m | `hive-swarm/swarm/models/task.py:L82-L85` | A08 | `task.fail("")` should raise instead of accept blank reason. |
| F-09C | low | 1m | `hive-swarm/swarm/models/state.py:L173-L174` | A09 | `add_error` should call `self.touch()`. |
| F-09D | low | 15m | `hive-swarm/swarm/models/state.py:L116-L121` | A09 | Document why `history` cap keeps `[:1] + [-(N-1):]` while `errors` cap keeps `[-N:]`. |
| F-19D | low | 5m | `hive-swarm/swarm/nodes/approval.py:L60-L66` | A19 | Document strict-literal decision parsing (typo "approved" denies). |
| F-20D | low | 1m | `hive-swarm/swarm/nodes/checkpointing.py:L33` | A20 | Use `secrets.token_hex(8)` instead of `(4)`. |
| F-23B | low | 5m | `hive-swarm/swarm/models/consensus.py:L160` | A23 | Zero-confidence success: set `agreement_fraction = best_count/len(votes)` (count-based) instead of 0.0. |
| F-25C | low | 15m | `hive-swarm/swarm/nodes/queen.py:L80` | A25 | Document that `adaptive == hierarchical` until F-15B implemented. |
| F-27C | low | 1m | `hive-swarm/swarm/models/state.py:L92` | A27 | Add `le=10_000` to `sona_cycle_count`. |

## Cross-cutting (W6 — package consolidation)

| ID | S | E | Description |
|---|---|---|---|
| F-W6A | high | 1d | Create `swarm-shared/` package with: `hashing.py`, `time.py`, `bounded_list.py`, `atomic_write.py`, `redaction.py`, `checkpointing.py` (one `BaseRedactingCheckpointer`), `memory_adapters.py` (`lesson_to_entry`). |
| F-W6B | med | 30m | Vendor `swarm-shared` into `hive-swarm`, `ai-coder-hardening-improved`, `ai-provider-swarm-gateway` via `pip install -e ../swarm-shared`. |
| F-W6C | low | 30m | Document the cross-project consolidation in each project's README. |

## Re-runs needed (incomplete fetches in this analysis)

| ID | Description |
|---|---|
| RR1 | Re-fetch `ai-provider-swarm-gateway/src/.../models/state.py`, `quota.py`, `credentials.py`, `consensus/strategies.py`, `dashboard/app.py`, `cli.py`, `policy/guardrails.py` |
| RR2 | Re-fetch `ai-coder-hardening-improved/src/ai_coder/workflow/nodes.py` chunk 2 (to verify C9/M1/M3 status of `fail_closed`, `_ensure_model_seed`, `build_graph`) |
| RR3 | Re-fetch `ai-coder-hardening-improved/src/ai_coder/` legacy workflow files (W4 verification) |
| RR4 | Re-fetch `ai-provider-swarm-gateway/src/.../providers/*.py` (per-adapter ABC conformance) |

---

## Summary counts
- **P0 critical:** 11
- **P1 high:** 21
- **P2 med:** 21
- **P3 low:** 13
- **Cross-cutting:** 3
- **Re-runs:** 4
- **Total fix items:** 73
