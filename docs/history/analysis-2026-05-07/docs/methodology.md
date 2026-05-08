# Methodology

Each of the 30 sub-agents follows the same 7-section template per file in scope:

1. **PURPOSE** — one-sentence mission
2. **PUBLIC SURFACE** — exported names + signatures
3. **WHAT WORKS ✅** — strengths, with `file:line` citations
4. **WHAT'S BROKEN 🔴** — categorised:
   - `SEC` security / secret / injection / traversal
   - `CORR` correctness / logic / race
   - `TYPE` Pydantic v2 schema gap
   - `LG` LangGraph misuse
   - `PERF` perf / unbounded growth
   - `OBS` observability gap
   - `TEST` missing/weak test
   - `DOC` doc drift
5. **WHAT'S MISSING 🟡** — implied but absent
6. **FIX RECOMMENDATION** — surgical sketch
7. **SEVERITY × EFFORT MATRIX** — `S: critical|high|med|low` × `E: 1h|1d|1wk`

## Finding ID convention

`<agent_NN>-<category><n>` — e.g. `09-T1` = first TYPE finding from agent 09.

This makes every finding cross-referenceable from `fix_plan.md` and `consensus_log.jsonl`.

## Consensus protocol used by the orchestrator

Disputed findings (where two agents disagreed) were resolved via:

| Dispute type | Protocol | Quorum |
|---|---|---|
| Security claim (`SEC`) | BFT | 2/3 of {Opus 4.6, Opus 4.7, Sonnet 4.6} |
| Architecture / design | Raft | Orchestrator (queen) is leader |
| Performance claim (`PERF`) | Majority | 50%+1 of agents that scored the file |
| Cross-cutting / soft | Gossip | confidence-weighted, threshold ≥ 0.7 |

All disputes logged to `consensus_log.jsonl`. In this run there were 7 disputes — see that file for the full audit trail.

## Anti-drift enforcement

Agent 05 (Anti-Drift Sentinel) reviewed every other agent's artefact and:
1. Computed each finding's distance from the canonical objective `analyse what works + what is broken/missing across swarmMain/`.
2. Vetoed any finding outside scope (e.g. "rewrite in Rust" — out of scope for an analysis run).
3. Confirmed `objective_hash` preserved end-to-end.

Final drift events: **0**. (See `agents/agent_05_anti_drift.md`.)

## Evidence rule

Every claim cites `path/to/file.py:Lstart-Lend`. No claim survives without evidence. Any finding that could not be cited was downgraded to "speculation" and excluded from `fix_plan.md`.
