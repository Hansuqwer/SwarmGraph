# Changelog

All notable changes to SwarmGraph are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) +
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each version links to its milestone doc and handover notes in
[docs/history/](docs/history/).

---

## [0.8.1] — 2026-05-09

**MCP toolbox + safety hardening**

### Added
- Optional `ai-provider-swarm-gateway[mcp-toolbox]` extra and
  `ai-provider-gateway mcp-toolbox` CLI group.
- MCP toolbox helpers for manifest output, generic MCP client config,
  Flutter project summary, and opt-in `serve` via the MCP SDK.

### Fixed
- Streaming HITL guard now force-checks accumulated text at stream completion,
  preventing short streams from bypassing throttled regex checks.
- Streaming HITL failures now emit dedicated `stream_hitl_decision` audit
  records before the related `worker_result`.
- S3 audit append now uses conditional create for missing audit objects to
  reduce first-writer lost-update races.
- JSONL and S3 audit append now reject sequence/hash boundary mismatches before
  extending persisted audit logs.
- Browser auth import now requires provider cookie domain suffix matches.
- 9router base URL validation now rejects non-loopback HTTP URLs.
- Gateway dispatcher now forwards `timeout_seconds` to adapters that accept it
  while preserving legacy adapter fallback.

---

## [0.8.0] — 2026-05-08

**Audit signing + Streaming HITL guards**

### Added
- `swarm_shared.audit` — `AuditRecord`, `AuditChain`, `sign_record`,
  `verify_chain`, `append_jsonl`, `load_jsonl_chain`
- HMAC-SHA256 signed audit records with chained `prev_hash` (insertion /
  deletion / reorder all break `verify_chain`)
- `SwarmConfig` fields: `audit_signing_enabled`, `audit_secret_env`,
  `audit_log_path` (supports `{tenant}` / `{swarm_id}` placeholders),
  `audit_kinds`
- `SwarmState` fields: `audit_records`, `audit_chain_head`, `audit_sequence`
- `_audit_helper.sign_and_record()` — called from consensus, approval, and
  collect-results nodes
- `StreamingHITLInterrupt` exception + `_StreamingGuard` per-chunk guard
- `SwarmConfig` streaming fields: `streaming_guard_patterns`,
  `streaming_max_output_chars`, `streaming_hitl_action_default`,
  `streaming_guard_check_every_n_chunks`
- `ai-provider-gateway audit verify <log> --secret-env HIVE_SWARM_AUDIT_SECRET`
- `_streaming_hitl_prompt()` CLI helper (interactive resume)

### Reference
- Prompt: [docs/history/orchestrator-prompts/08_v8.md](docs/history/orchestrator-prompts/08_v8.md)
- Handover: [docs/history/patches/cli_handover_patch_v8/HANDOVER_PATCH_v8.md](docs/history/patches/cli_handover_patch_v8/HANDOVER_PATCH_v8.md)

---

## [0.7.1] — 2026-05-07

**Canonicalization + quota reset fix**

### Fixed
- `QuotaTracker.reset_usage()` now bypasses max-merge via `_authoritative_save_locked()`;
  reset always writes zero regardless of concurrent disk state
- `quota show --since` now hides zero-usage rows correctly
- `_maybe_reset()` also uses authoritative save

### Reference
- Prompt: [docs/history/orchestrator-prompts/07.1_v7.1.md](docs/history/orchestrator-prompts/07.1_v7.1.md)
- Handover: [docs/history/patches/cli_handover_patch_v7.1/HANDOVER_PATCH_v7.1.md](docs/history/patches/cli_handover_patch_v7.1/HANDOVER_PATCH_v7.1.md)

---

## [0.7.0] — 2026-05-07

**Multi-tenant quota + OpenAI embeddings + Interactive HITL**

### Added
- Multi-tenant quota isolation (`--tenant` flag on all `quota` subcommands)
- `ai-provider-gateway tenants` subcommand group
- OpenAI embedding adapter (`OpenAIEmbeddingAdapter`) + `default_embedder_from_env()`
- `HashEmbedder` for deterministic stub embeddings
- Interactive HITL approval prompt in `ai-provider-gateway swarm`
  (single-use token, Rich panel display)
- `approval_consumed` guard (F-19A): prevents replay attacks
- `WorkerResult.to_vote()` truncates `proposed_action` to 2048 chars
- Collect-results node avoids re-emitting accumulated `worker_results`
- Worker result deduplication reducer in `factory.py`

### Reference
- Prompt: [docs/history/orchestrator-prompts/07_v7.md](docs/history/orchestrator-prompts/07_v7.md)
- Handover: [docs/history/patches/cli_handover_patch_v7/HANDOVER_PATCH_v7.md](docs/history/patches/cli_handover_patch_v7/HANDOVER_PATCH_v7.md)

---

## [0.6.0] — 2026-05-07

**Embedding anti-drift + streaming + cost tracking + CLI ergonomics**

### Added
- 3-mode anti-drift: `off` / `keyword` / `embedding` (`SwarmConfig.anti_drift_mode`)
- Cosine similarity drift detection via pluggable `EmbeddingProvider`
- `GatewayEmbedder` using the provider gateway
- `llm_stream_enabled` — opt-in streaming with `dispatch_stream()`
- `cost_tracking_enabled` — per-call USD cost from `swarm_shared.pricing`
- `WorkerResult.usage` (`TokenUsage`) with `cost_usd`
- `ai-provider-gateway quota show --since <duration>` filter
- Rich-escaped quota messages (F-30-COSM1)
- `F-18-CORR2`: `anti_drift_similarity_threshold=0` coalesces to mode=off

### Reference
- Prompt: [docs/history/orchestrator-prompts/06_v6.md](docs/history/orchestrator-prompts/06_v6.md)
- Handover: [docs/history/patches/cli_handover_patch_v6_ergonomics/HANDOVER_PATCH_v6.md](docs/history/patches/cli_handover_patch_v6_ergonomics/HANDOVER_PATCH_v6.md)

---

## [0.5.0] — 2026-05-07

**Tier-2 routing + per-role model overrides + token usage + swarm CLI**

### Added
- 3-tier complexity routing: `tier1_fast` / `tier2_medium` / `tier3_swarm`
- `llm_role_provider_overrides` + `llm_role_model_overrides` in `SwarmConfig`
- Queen forwards `llm_settings` (including per-role overrides) to workers via `QueenDirective`
- `TokenUsage` model populated from gateway responses
- `ai-provider-gateway swarm` subcommand (run a full swarm from CLI)
- `--show-workers`, `--json`, `--stream`, `--anti-drift` flags
- `HIVE_SWARM_COST_TRACKING` env var (F-17-ENV1)
- `HIVE_SWARM_LLM_STREAM` env var

### Reference
- Prompt: [docs/history/orchestrator-prompts/05_v5.md](docs/history/orchestrator-prompts/05_v5.md)
- Handover: [docs/history/patches/cli_handover_patch_v5/HANDOVER_PATCH_v5.md](docs/history/patches/cli_handover_patch_v5/HANDOVER_PATCH_v5.md)

---

## [0.4.0] — 2026-05-07

**Workers through gateway**

### Added
- `hive-swarm` workers call `ai-provider-swarm-gateway` in opt-in mode
  (`llm_backend="gateway"`)
- `GatewayDispatcher` fully integrated into worker dispatch loop
- `ai-provider-gateway swarm` added (v1)
- Live anti-drift verification against 9router endpoint
- 9router response body quirk handled (`body.split("data:", 1)[0].strip()`)

### Reference
- Prompt: [docs/history/orchestrator-prompts/04_gateway.md](docs/history/orchestrator-prompts/04_gateway.md)
- Handover: [docs/history/patches/cli_handover_patch_v4_workers/HANDOVER_PATCH_v4.md](docs/history/patches/cli_handover_patch_v4_workers/HANDOVER_PATCH_v4.md)

---

## [0.3.0] — 2026-05-07

**9router live + gateway registry**

### Added
- `NineRouterAdapter` — OpenAI-compatible adapter for 9router endpoint
- Registry entry for 9router in `providers.yaml`
- `Capability` enum patched to include `"video"`
- Live route confirmed: `"selected_provider": "9router"`, `"response_text": "pong"`
- `ai-provider-gateway providers list`, `route`, `inspect-state` working

### Reference
- Handover: [docs/history/patches/cli_handover_patch_v3/HANDOVER_PATCH_9ROUTER.md](docs/history/patches/cli_handover_patch_v3/HANDOVER_PATCH_9ROUTER.md)

---

## [0.2.0] — 2026-05-07

**CLI scaffold + gateway wiring**

### Added
- `ai-provider-gateway` CLI (Typer) with `quota`, `providers`, `route` subcommands
- Editable installs for `swarm-shared`, `hive-swarm`, `ai-provider-swarm-gateway`
- Upstream gateway RR1 modules vendored: `models/`, `graph/`, `consensus/`,
  `policy/`, `providers/`, `registry/`
- Pydantic validator recursion fix via `object.__setattr__`
- `SwarmMemory.max_entries ge=1`

### Reference
- Handover: [docs/history/patches/cli_handover_patch_v2/HANDOVER_PATCH_CLI_V2.md](docs/history/patches/cli_handover_patch_v2/HANDOVER_PATCH_CLI_V2.md)

---

## [0.1.0] — 2026-05-07

**Initial analysis baseline**

### Added
- 30-agent hive analysis of existing `pylangSWARM` workspace
- Pydantic v2 discipline applied across all models
- LangGraph `Send`-based conditional fan-out (queen → workers)
- BFT / Raft / simple-majority consensus protocols
- `SwarmConfig`, `SwarmState`, `SwarmCheckpoint` models
- `swarm-shared` package: `atomic_write`, `bounded_list`, `hashing`,
  `pricing`, `redaction`, `checkpointing`
- Stub dispatcher (zero-network default)
- `pytest` suites across all three packages

### Reference
- Analysis: [docs/history/HIVE_ANALYSIS_REPORT.md](docs/history/HIVE_ANALYSIS_REPORT.md)
- Prompt: [docs/history/orchestrator-prompts/00_analysis.md](docs/history/orchestrator-prompts/00_analysis.md)

---

[0.8.1]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.8.1
[0.8.0]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.8.0
[0.7.1]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.7.1
[0.7.0]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.7.0
[0.6.0]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.6.0
[0.5.0]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.5.0
[0.4.0]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.4.0
[0.3.0]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.3.0
[0.2.0]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.2.0
[0.1.0]: https://github.com/Hansuqwer/SwarmGraph/releases/tag/v0.1.0
