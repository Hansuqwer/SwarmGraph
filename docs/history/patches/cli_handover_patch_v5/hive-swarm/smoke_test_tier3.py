"""Tier-3 smoke test — exercises the queen→worker→gateway path.

Unlike the original smoke_test.py (whose objective lands in tier-1 fast path),
this objective is verbose + complex enough to land in tier-3, which spawns
real workers via Send fan-out.

Stub mode (default):
    python smoke_test_tier3.py
        → workers return deterministic strings; same back-compat behaviour.

Gateway mode (real LLM):
    HIVE_SWARM_LLM_BACKEND=gateway \\
    AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \\
        python smoke_test_tier3.py
        → workers route through 9router; final_output contains real LLM text;
          token totals printed at the end.
"""
from __future__ import annotations

import os
import sys

from swarm import SwarmConfig, SwarmState, build_swarm_graph

# ── Tier-3 objective (verbose enough to clear router thresholds) ─────────

OBJECTIVE = (
    "Implement a comprehensive distributed authentication architecture for a "
    "multi-tenant SaaS platform with OAuth2, refresh tokens, role-based access "
    "control, audit logging, and Pydantic v2 typed boundaries. Include "
    "concurrent session handling and a security review."
)


def main() -> int:
    backend = os.environ.get("HIVE_SWARM_LLM_BACKEND", "stub")

    config = SwarmConfig(
        topology="hierarchical",
        consensus_protocol="raft",
        max_agents=5,
        sona_enabled=True,
        # Set risk threshold high so non-interactive runs don't HITL-pause.
        require_approval_above_risk=0.95,
        # Default = stub; env var HIVE_SWARM_LLM_BACKEND=gateway flips it.
    )
    state = SwarmState(
        swarm_id="tier3-smoke",
        objective=OBJECTIVE,
        config=config,
    )

    print(f"# objective hash: {state.objective_hash}")
    print(f"# llm backend:    {backend}")
    print(f"# topology:       {config.topology}")
    print(f"# consensus:      {config.consensus_protocol}")
    print()

    graph = build_swarm_graph(config)
    result = graph.invoke(
        state.to_json_dict(),
        config={"configurable": {"thread_id": "tier3-smoke-thread"}},
    )
    final = SwarmState.from_json_dict(result)

    print(f"Status:          {final.status}")
    print(f"Failure cause:   {final.failure_cause}")
    print(f"Iterations:      {final.iteration}")
    print(f"SONA cycles:     {final.sona_cycle_count}")
    print(f"Worker count:    {len(final.worker_results)}")
    print()

    # Token totals across workers (v5)
    total_in = sum((r.usage.input_tokens if r.usage else 0) for r in final.worker_results)
    total_out = sum((r.usage.output_tokens if r.usage else 0) for r in final.worker_results)
    print(f"Total input tokens:  {total_in}")
    print(f"Total output tokens: {total_out}")
    print()

    # Per-worker breakdown
    print("Per-worker results:")
    for r in final.worker_results:
        usage = r.usage
        usage_str = (
            f"in={usage.input_tokens} out={usage.output_tokens} model={usage.model_id_used}"
            if usage else "(no usage)"
        )
        outline = (r.output[:120] + "…") if len(r.output) > 120 else r.output
        ok = "✓" if r.success else "✗"
        print(f"  {ok} {r.agent_role:12s} {usage_str}")
        print(f"      output: {outline}")

    print()
    print(f"Final output:    {final.final_output[:200]}{'…' if len(final.final_output) > 200 else ''}")

    if final.status in ("completed",):
        return 0
    if final.status in ("awaiting_approval",):
        print("⚠️  Run paused for HITL approval (raise require_approval_above_risk to skip).")
        return 0
    print(f"⚠️  Run did not complete cleanly: status={final.status}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
