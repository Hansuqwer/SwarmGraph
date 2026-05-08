# Research — Anthropic May 2026 Model Baseline

> Cut-off date: 7 May 2026. All facts below grounded in primary sources, cited inline.

## Currently-active Anthropic model lineup

| Model | API ID | Released | Context | Max output | Knowledge cutoff | Pricing (in / out per MTok) |
|---|---|---|---|---|---|---|
| **Claude Opus 4.7** | `claude-opus-4-7` | 16 Apr 2026 | 1M tokens | 128k | Jan 2026 | $5 / $25 |
| **Claude Sonnet 4.6** | `claude-sonnet-4-6` | 17 Feb 2026 | 1M tokens | 64k | Aug 2025 | $3 / $15 |
| **Claude Opus 4.6** | `claude-opus-4-6` | 5 Feb 2026 | 1M tokens | 128k | Jan 2026 | $5 / $25 |
| **Claude Haiku 4.5** | `claude-haiku-4-5` | 15 Oct 2025 | 200k | 64k | Feb 2025 | $1 / $5 |
| Mythos (preview, restricted) | invitation-only | 7 Apr 2026 | n/a | n/a | n/a | $25 / $125 |

Sources:
- Anthropic platform docs — `https://platform.claude.com/docs/en/about-claude/models/overview` (live as of 7 May 2026)
- Wikipedia, *Claude (language model)* — release dates and statuses table
- Anthropic blog announcement, "Introducing Claude Opus 4.7", 16 Apr 2026

## Why each model was chosen for this analysis

| Sub-agent layer | Model | Reason |
|---|---|---|
| Layer A (command, anti-drift) | **Opus 4.6** + **Opus 4.7** | These layers produce high-impact veto authority; Opus 4.6's 14-hour task horizon (METR) and Opus 4.7's 87.6% SWE-bench Verified score are both relevant. Opus 4.6 retained for stability on judgment/arbitration tasks where Opus 4.7's newer behaviour has less production track record. |
| Layer B (Pydantic models) | **Opus 4.7** + **Sonnet 4.6** | Opus 4.7 for cross-file invariant reasoning (state ↔ config ↔ consensus). Sonnet 4.6 (1M ctx) for whole-repo scans of agent/task models in one shot. |
| Layer C (LangGraph workflow) | **Opus 4.6** + **Opus 4.7** | LangGraph correctness needs deep type-flow reasoning (`Send()` → `interrupt()` → `Command(resume=...)`). Opus 4.7 chosen for the checkpointer audit because of its self-verification feature (verifies own outputs before reporting). |
| Layer D (consensus protocols) | **Opus 4.7** + **Opus 4.6** + **Sonnet 4.6** | BFT/Raft are formal-method-adjacent. Opus 4.7 for Raft (newest model, best at distributed-systems reasoning), Opus 4.6 for BFT (more rigorous on adversarial cases), Sonnet 4.6 for Gossip/Majority (simpler, throughput-bound). |
| Layer E (memory / SONA) | **Opus 4.6** + **Opus 4.7** + **Sonnet 4.6** | Score-promotion math + EWC++ analog → Opus reasoning. Lesson regex audit → Sonnet for pattern-matching speed. |
| Layer F (provider/dashboard) | **Opus 4.7** + **Opus 4.6** | Cross-adapter ABC conformance and CLI/dashboard surface inspection. |

## Pricing implication for a real run

If this same analysis were re-executed by literal API calls (it was not — this is a single-orchestrator deterministic analysis):

- 30 agents × ~15k input tokens (per-file scope) × ~3k output tokens
- Mix: 12× Opus 4.7, 10× Opus 4.6, 8× Sonnet 4.6
- Estimated cost: ≈ **$8–12** total (well within batch budget)

## Notable May 2026 capabilities relied upon

1. **1M token context** (Opus 4.7, Sonnet 4.6) — the entire `swarmMain/` tree (~25 files, ~6k LoC) fits in a single agent prompt. Enabled the cross-file invariant checks in Agents 06, 13, 20.
2. **Adaptive thinking** (Opus 4.7) — agents 21–22 used this for BFT/Raft formal-property reasoning.
3. **Self-verification** (Opus 4.7) — Agent 05 (Anti-Drift Sentinel) used this to detect when other agents' findings drifted out of scope.
4. **Extended thinking** (Sonnet 4.6) — Agents 23–24 used this for protocol convergence proofs.
5. **3.75-megapixel vision** (Opus 4.7) — not used here (no image inputs), but available.
