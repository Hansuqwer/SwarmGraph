# Patch note — ruflo-swarm-prompt (2026-05-07)

This sub-project is documentation-only (`RUFLO_RESEARCH_NOTES.md`,
`RUFLO_SWARM_PYDANTIC_LANGGRAPH_PROMPT.md`). No code edits required.

The Ruflo→Python mapping verification (which rows are ✅ / ⚠️ / ❌) lives in
`hive_analysis_project/ruflo_mapping_check.md`. After this patch run, several
rows previously marked ⚠️ should be re-evaluated:

| Row | Was | Now |
|---|---|---|
| Adaptive topology (#8) | ❌ aliased | ⚠️ → ✅ — `_adaptive_decompose` now escalates to mesh on prior_agreement < 0.5 |
| Raft consensus (#9) | ⚠️ leader-decides | ⚠️ → improved — split-brain detection + follower-aware agreement (still not full Raft) |
| BFT consensus (#10) | ⚠️ unanimity at n=3 | ✅ — textbook formula + n>=4 guard + agent de-dupe |
| Gossip consensus (#11) | ⚠️ single-round | ⚠️ — improved with confidence_floor; still single-round (true gossip remains a future item) |
| CRDT/Majority (#12) | ⚠️ misnomer | ⚠️ — first-proposer tie-break replaces alphabetical bias; CRDT semantics still absent |
| EWC++ (#16) | ❌ misnamed | ⚠️ — promote_score now preserves `created_at` (no longer a 1-line bump that resets age); still not Fisher-weighted |
| Claims (human gate) (#17) | ⚠️ no guard | ✅ — single-use `approval_consumed` + typed `ApprovalDecision` + decision_token |
| Secret redaction (#20) | ⚠️ toy regex | ✅ — production regex set via `swarm_shared.redaction` |

A full re-verified table belongs in `ruflo_mapping_check.md` after this patch run.
