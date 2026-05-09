"""Worker node — patched (v8: streaming HITL + audit signing).

History:
  F-16A, F-16B, F-16-CORR1, v4 dispatcher, v5 usage propagation
v6: populates WorkerResult.usage.cost_usd via swarm_shared.pricing;
    consumes dispatch_stream when llm_settings.stream_enabled is True
    (concatenates chunks into final text — same WorkerResult shape).
v8: StreamingHITLInterrupt caught in worker_node; collect_results_node
    signs each worker_result via _audit_helper.sign_and_record().
"""

from __future__ import annotations

from typing import Any

from .._audit_helper import sign_and_record
from ..llm import (
    StreamChunk,
    WorkerLLMError,
    WorkerLLMResponse,
    build_dispatcher,
    estimate_call_cost,
    resolve_llm_settings,
)
from ..llm.dispatch import StreamingHITLInterrupt  # v8
from ..models.agent import AgentState, TokenUsage, WorkerResult
from ..models.state import SwarmState


def _to_token_usage(
    resp: Any,
    *,
    cost_tracking_enabled: bool = True,
) -> TokenUsage | None:
    """Build a TokenUsage from a WorkerLLMResponse if any usage data is present."""
    if resp is None:
        return None
    in_t = getattr(resp, "input_tokens", 0) or 0
    out_t = getattr(resp, "output_tokens", 0) or 0
    model_id = getattr(resp, "model_id_used", "") or ""
    finish_reason = getattr(resp, "finish_reason", "") or ""
    provider_id = getattr(resp, "provider_id", "") or ""
    if not any([in_t, out_t, model_id, finish_reason, provider_id]):
        return None

    cost: float | None = None
    if cost_tracking_enabled and (in_t or out_t):
        try:
            cost = estimate_call_cost(model_id, in_t, out_t)
        except Exception:
            cost = None

    return TokenUsage(
        input_tokens=in_t,
        output_tokens=out_t,
        model_id_used=model_id[:256],
        finish_reason=finish_reason[:64],
        provider_id=provider_id[:64],
        cost_usd=cost,
    )


def _consume_stream_to_response(
    chunks_iter,
    *,
    fallback_provider_id: str,
    fallback_model_id: str,
) -> WorkerLLMResponse:
    """Collapse a stream iterator into a WorkerLLMResponse.

    Token counts are typically unavailable in chunks, so we leave them at 0.
    The model_id and finish_reason are pulled from the final chunk.
    """
    accumulated = ""
    finish = ""
    for chunk in chunks_iter:
        if isinstance(chunk, StreamChunk):
            if chunk.text:
                accumulated += chunk.text
            if chunk.done:
                finish = chunk.finish_reason or finish
        else:
            # Defensive: shouldn't happen but tolerate raw strings
            accumulated += str(chunk)
    return WorkerLLMResponse(
        text=accumulated,
        backend="gateway",
        latency_ms=0,
        input_tokens=0,
        output_tokens=0,
        model_id_used=fallback_model_id or "unknown",
        finish_reason=finish or "stop",
        provider_id=fallback_provider_id,
    )


def worker_node(agent_state_dict: dict[str, Any]) -> dict[str, Any]:
    """LangGraph worker. Returns reducer-friendly {"worker_results": [...]}."""
    agent_state = AgentState.model_validate(agent_state_dict)
    agent_state.mark_started()

    try:
        settings = resolve_llm_settings(agent_state.task_context, agent_state.role)
        dispatcher = build_dispatcher(settings)
        cost_tracking = bool(settings.get("cost_tracking_enabled", True))
        stream_enabled = bool(settings.get("stream_enabled", False))

        if stream_enabled and hasattr(dispatcher, "dispatch_stream"):
            stream = dispatcher.dispatch_stream(
                role=agent_state.role,
                task_description=agent_state.task_description,
                context=agent_state.task_context,
            )
            try:
                resp = _consume_stream_to_response(
                    stream,
                    fallback_provider_id=settings.get("effective_provider", ""),
                    fallback_model_id=settings.get("effective_model", ""),
                )
            except StreamingHITLInterrupt as si:
                # v8: convert to failed WorkerResult with partial text metadata
                agent_state.mark_failed(f"stream_hitl: {si.reason}")
                result = WorkerResult(
                    agent_id=agent_state.agent_id,
                    agent_role=agent_state.role,
                    task_id=agent_state.assigned_task_id or "unknown",
                    success=False,
                    error_message=f"stream_hitl: {si.reason}",
                    confidence=0.0,
                    duration_seconds=agent_state.duration_seconds() or 0.0,
                    metadata={
                        "stream_hitl_reason": si.reason,
                        "stream_hitl_partial_chars": len(si.partial_text),
                        "stream_hitl_partial_preview": si.partial_text[:500],
                    },
                )
                return {"worker_results": [result.model_dump(mode="json")]}
        else:
            resp = dispatcher.dispatch_full(
                role=agent_state.role,
                task_description=agent_state.task_description,
                context=agent_state.task_context,
            )

        output = resp.text
        confidence = _estimate_confidence(output, agent_state.task_description)
        agent_state.mark_done(output, confidence)

        usage = _to_token_usage(resp, cost_tracking_enabled=cost_tracking)
        result = WorkerResult(
            agent_id=agent_state.agent_id,
            agent_role=agent_state.role,
            task_id=agent_state.assigned_task_id or "unknown",
            success=True,
            output=output,
            confidence=confidence,
            duration_seconds=agent_state.duration_seconds() or 0.0,
            metadata={
                "llm_backend": settings.get("backend", "stub"),
                "llm_provider": settings.get("effective_provider", ""),
                "llm_latency_ms": getattr(resp, "latency_ms", 0),
                "llm_streamed": stream_enabled,
            },
            usage=usage,
        )
    except WorkerLLMError as exc:
        agent_state.mark_failed(f"llm_error: {exc}")
        result = WorkerResult(
            agent_id=agent_state.agent_id,
            agent_role=agent_state.role,
            task_id=agent_state.assigned_task_id or "unknown",
            success=False,
            error_message=f"llm_error: {exc}",
            confidence=0.0,
            duration_seconds=agent_state.duration_seconds() or 0.0,
        )
    except Exception as exc:
        agent_state.mark_failed(str(exc))
        result = WorkerResult(
            agent_id=agent_state.agent_id,
            agent_role=agent_state.role,
            task_id=agent_state.assigned_task_id or "unknown",
            success=False,
            error_message=str(exc),
            confidence=0.0,
            duration_seconds=agent_state.duration_seconds() or 0.0,
        )

    return {"worker_results": [result.model_dump(mode="json")]}


def _estimate_confidence(output: str, task_desc: str) -> float:
    if not output.strip():
        return 0.0
    task_tokens = set(task_desc.lower().split())
    out_tokens = set(output.lower().split())
    union = task_tokens | out_tokens
    overlap = len(task_tokens & out_tokens) / max(len(union), 1)
    length_score = min(len(output) / 500.0, 0.5)
    return round(min(1.0, overlap * 0.5 + length_score), 3)


def collect_results_node(state: dict[str, Any]) -> dict[str, Any]:
    swarm = SwarmState.model_validate(state)
    swarm.status = "voting"

    new_votes = [r.to_vote(round_id=swarm.consensus_round_id) for r in swarm.worker_results]
    for vote in new_votes:
        swarm.collect_vote(vote)

    for r in swarm.worker_results:
        if r.success:
            try:
                swarm.mark_task_complete(r.task_id, r.output)
            except ValueError:
                pass

    total_in = sum((r.usage.input_tokens if r.usage else 0) for r in swarm.worker_results)
    total_out = sum((r.usage.output_tokens if r.usage else 0) for r in swarm.worker_results)
    # v6: roll up cost (sum of populated cost_usd; None values skipped)
    total_cost = sum(
        (r.usage.cost_usd if (r.usage and r.usage.cost_usd is not None) else 0.0)
        for r in swarm.worker_results
    )

    swarm.append_history(
        "consensus",
        {
            "node": "collect_results",
            "vote_count": len(new_votes),
            "worker_count": len(swarm.worker_results),
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_cost_usd": round(total_cost, 6),
        },
    )

    # v8: sign each worker_result event (in collect_results_node where we
    # have full SwarmState). Each result is one signed audit record.
    for r in swarm.worker_results:
        sign_and_record(
            swarm,
            "worker_result",
            {
                "agent_id": r.agent_id,
                "agent_role": r.agent_role,
                "task_id": r.task_id,
                "success": r.success,
                "output_hash": r.output_hash,
                "output_preview": (r.output or r.error_message)[:500],
                "confidence": r.confidence,
                "duration_seconds": r.duration_seconds,
                "input_tokens": r.usage.input_tokens if r.usage else 0,
                "output_tokens": r.usage.output_tokens if r.usage else 0,
                "model_id_used": r.usage.model_id_used if r.usage else "",
                "cost_usd": r.usage.cost_usd if r.usage else None,
            },
        )

    swarm.touch()
    out = swarm.to_json_dict()
    # worker_results uses operator.add in LangGraph; returning the accumulated
    # list from this collector would append it to itself on every iteration.
    out.pop("worker_results", None)
    return out


__all__ = [
    "worker_node",
    "collect_results_node",
    "_estimate_confidence",
    "_to_token_usage",
    "_consume_stream_to_response",
]
