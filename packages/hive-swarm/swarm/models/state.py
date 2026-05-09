"""SwarmState + SwarmCheckpoint — patched (v8: audit_records field).

History (v4–v7.1) preserved.
v8: SwarmState gains `audit_records: list[dict]` — JSON-serializable
    audit chain in-memory. Persistent JSONL flush is handled by individual
    nodes (consensus/approval/worker) when SwarmConfig.audit_log_path is set.

Why dict not AuditRecord:
    LangGraph state is JSON-roundtripped at every node boundary. Storing
    AuditRecord directly would either force a custom serializer per
    Pydantic v2 invocation OR require AuditRecord to live in this same
    module. Storing as dict keeps the cross-package boundary clean and
    matches the existing `worker_results` / `history` patterns.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from swarm_shared.bounded_list import CappedListConfig, cap_list

from ..llm.embeddings import (
    EmbeddingProvider,
    NullEmbedder,
    cosine_similarity,
    get_default_embedder,
)
from .agent import AgentSpec, AgentVote, WorkerResult
from .base import HardenedModel, now_ts, stable_hash
from .config import SwarmConfig
from .consensus import ConsensusResult
from .memory import SwarmMemory
from .task import SwarmTask
from .types import (
    ComplexityTier,
    HistoryKind,
    SwarmFailureCause,
    SwarmStatus,
)

_HISTORY_CFG = CappedListConfig(max_len=500, keep_strategy="head_plus_tail")
_ERRORS_CFG = CappedListConfig(max_len=100, keep_strategy="tail")
_AUDIT_RECORDS_CFG = CappedListConfig(max_len=10_000, keep_strategy="tail")
_MAX_AGENTS: int = 100
_MAX_RETRIEVED_CONTEXT = 10


class SwarmState(HardenedModel):
    """Canonical LangGraph shared state."""

    swarm_id: str = Field(..., min_length=1, max_length=128)
    objective: str = Field(..., min_length=1, max_length=8192)
    objective_hash: str = Field(default="")
    schema_version: int = Field(default=1, ge=1)

    config: SwarmConfig

    agents: list[AgentSpec] = Field(default_factory=list)

    tasks: list[SwarmTask] = Field(default_factory=list)
    current_task_id: str | None = None
    completed_task_ids: list[str] = Field(default_factory=list)

    complexity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    complexity_tier: ComplexityTier = "tier3_swarm"

    pending_votes: list[AgentVote] = Field(default_factory=list)
    consensus_result: ConsensusResult | None = None
    consensus_round_id: str = ""

    worker_results: list[WorkerResult] = Field(default_factory=list)
    latest_output: str = ""
    latest_output_hash: str = ""
    final_output: str = ""

    memory: SwarmMemory = Field(default_factory=SwarmMemory)
    sona_distilled: bool = False
    sona_cycle_count: int = Field(default=0, ge=0, le=10_000)
    retrieved_context: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=_MAX_RETRIEVED_CONTEXT,
    )

    status: SwarmStatus = "initializing"
    failure_cause: SwarmFailureCause | None = None
    iteration: int = Field(default=0, ge=0)

    approval_consumed: bool = False
    approval_decision_token: str = ""

    # v8: streaming HITL guard
    stream_hitl_pending: bool = False
    stream_hitl_partial_text: str = ""
    stream_hitl_trigger_reason: str = ""
    stream_hitl_decision_token: str = ""

    history: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # v8: signed audit chain (JSON-serializable AuditRecord dicts)
    audit_records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="HMAC-SHA256 signed audit records; populated when audit_signing_enabled.",
    )
    audit_chain_head: str = Field(
        default="",
        description="Most recent record_hash; new records use this as prev_hash.",
    )
    audit_sequence: int = Field(
        default=0,
        ge=0,
        description="Monotonic counter for the next audit record's sequence field.",
    )
    runtime_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Node-generated runtime hints; not persisted config.",
    )

    created_at: float = Field(default_factory=now_ts)
    updated_at: float = Field(default_factory=now_ts)

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("swarm_id")
    @classmethod
    def _id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("swarm_id must not contain spaces")
        return v

    @field_validator("agents")
    @classmethod
    def _agents_bounded(cls, v: list[AgentSpec]) -> list[AgentSpec]:
        if len(v) > _MAX_AGENTS:
            raise ValueError(f"agents list exceeds maximum of {_MAX_AGENTS}")
        return v

    @model_validator(mode="after")
    def _auto_objective_hash(self) -> "SwarmState":
        if not self.objective_hash:
            self.objective_hash = stable_hash(self.objective)
        return self

    @model_validator(mode="after")
    def _cap_lists(self) -> "SwarmState":
        new_history = cap_list(self.history, _HISTORY_CFG)
        if new_history is not self.history:
            self.history = new_history
        new_errors = cap_list(self.errors, _ERRORS_CFG)
        if new_errors is not self.errors:
            self.errors = new_errors
        new_audit = cap_list(self.audit_records, _AUDIT_RECORDS_CFG)
        if new_audit is not self.audit_records:
            self.audit_records = new_audit
        return self

    @model_validator(mode="after")
    def _agent_count_le_config(self) -> "SwarmState":
        if len(self.agents) > self.config.max_agents:
            raise ValueError(
                f"agents count ({len(self.agents)}) exceeds "
                f"config.max_agents ({self.config.max_agents})"
            )
        return self

    # ── Anti-drift (3-mode dispatch from v6 + F-18-CORR2) ─────────────────

    def check_drift(
        self,
        candidate_output: str,
        *,
        embedder: EmbeddingProvider | None = None,
    ) -> bool:
        if not self.config.anti_drift_enabled:
            return True
        if self.config.anti_drift_similarity_threshold == 0.0:
            return True

        mode = getattr(self.config, "anti_drift_mode", "keyword")
        if mode == "off":
            return True
        if mode == "embedding":
            return self._check_drift_embedding(candidate_output, embedder)
        return self._check_drift_keyword(candidate_output)

    def _check_drift_keyword(self, candidate_output: str) -> bool:
        obj_tokens = set(self.objective.lower().split())
        out_tokens = set(candidate_output.lower().split())
        if not obj_tokens:
            return True
        overlap = len(obj_tokens & out_tokens) / len(obj_tokens)
        return overlap >= self.config.anti_drift_similarity_threshold

    def _check_drift_embedding(
        self,
        candidate_output: str,
        embedder: EmbeddingProvider | None,
    ) -> bool:
        emb = embedder if embedder is not None else get_default_embedder()
        if isinstance(emb, NullEmbedder):
            return self._check_drift_keyword(candidate_output)
        try:
            obj_vec = emb.embed(self.objective)
            out_vec = emb.embed(candidate_output)
        except Exception:
            return self._check_drift_keyword(candidate_output)
        if not obj_vec or not out_vec:
            return self._check_drift_keyword(candidate_output)
        sim = cosine_similarity(obj_vec, out_vec)
        return sim >= self.config.anti_drift_similarity_threshold

    def assert_no_drift(
        self,
        candidate_output: str,
        *,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        if not self.check_drift(candidate_output, embedder=embedder):
            msg = (
                f"Anti-drift violation: output does not satisfy objective "
                f"(hash={self.objective_hash}, mode={getattr(self.config, 'anti_drift_mode', 'keyword')})"
            )
            self.status = "drifted"
            self.failure_cause = "objective_drift"
            raise ValueError(msg)

    # ── Mutation helpers ──────────────────────────────────────────────────

    def touch(self) -> None:
        self.updated_at = now_ts()

    def add_error(self, msg: str) -> None:
        self.errors = cap_list(self.errors + [msg], _ERRORS_CFG)
        self.touch()

    def append_history(self, kind: HistoryKind, payload: dict[str, Any]) -> None:
        entry: dict[str, Any] = {"kind": kind, "ts": now_ts(), **payload}
        self.history = cap_list(self.history + [entry], _HISTORY_CFG)

    def append_audit_record(self, record_dict: dict[str, Any]) -> None:
        """v8: append a signed audit record dict to the chain.

        Caller (consensus_node, approval_node, worker_node) is responsible for
        producing the signed dict via swarm_shared.audit.sign_record(). This
        method just appends it to state and updates head/sequence trackers.
        """
        self.audit_records = cap_list(self.audit_records + [record_dict], _AUDIT_RECORDS_CFG)
        self.audit_chain_head = str(record_dict.get("record_hash", ""))
        self.audit_sequence = int(record_dict.get("sequence", self.audit_sequence)) + 1

    def get_pending_tasks(self) -> list[SwarmTask]:
        done_ids = set(self.completed_task_ids)
        return [t for t in self.tasks if t.is_ready(done_ids) and t.status == "pending"]

    def mark_task_complete(self, task_id: str, result: str) -> None:
        for task in self.tasks:
            if task.task_id == task_id:
                task.complete(result)
                if task_id not in self.completed_task_ids:
                    self.completed_task_ids = self.completed_task_ids + [task_id]
                break

    def register_agent(self, spec: AgentSpec) -> None:
        if len(self.agents) >= self.config.max_agents:
            raise ValueError(f"Cannot register more than {self.config.max_agents} agents")
        self.agents = self.agents + [spec]

    def collect_vote(self, vote: AgentVote) -> None:
        self.pending_votes = self.pending_votes + [vote]

    def record_worker_result(self, result: WorkerResult) -> None:
        self.worker_results = self.worker_results + [result]
        if result.success:
            self.latest_output = result.output
            self.latest_output_hash = result.output_hash

    def increment_sona(self) -> None:
        self.sona_cycle_count += 1
        self.sona_distilled = True

    def fail(self, cause: SwarmFailureCause, reason: str = "") -> None:
        self.status = "failed"
        self.failure_cause = cause
        if reason:
            self.add_error(reason)

    def reset_for_retry(self) -> None:
        self.worker_results = []
        self.consensus_result = None
        self.pending_votes = []
        self.latest_output = ""
        self.latest_output_hash = ""
        self.status = "routing"
        # v8: streaming HITL fields reset too
        self.stream_hitl_pending = False
        self.stream_hitl_partial_text = ""
        self.stream_hitl_trigger_reason = ""
        # Reset an ephemeral HITL token field; this is not a hardcoded secret.
        self.stream_hitl_decision_token = ""  # nosec B105

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "SwarmState":
        return cls.model_validate(data)


class SwarmCheckpoint(HardenedModel):
    """Serializable point-in-time snapshot."""

    checkpoint_id: str = Field(..., min_length=1)
    swarm_id: str
    objective_hash: str
    state_snapshot: dict[str, Any]
    created_at: float = Field(default_factory=now_ts)
    iteration: int = Field(ge=0, default=0)
    status_at_checkpoint: SwarmStatus = "initializing"
    schema_version: int = Field(default=1, ge=1)

    @classmethod
    def from_state(cls, state: SwarmState, checkpoint_id: str) -> "SwarmCheckpoint":
        return cls(
            checkpoint_id=checkpoint_id,
            swarm_id=state.swarm_id,
            objective_hash=state.objective_hash,
            state_snapshot=state.to_json_dict(),
            iteration=state.iteration,
            status_at_checkpoint=state.status,
            schema_version=state.schema_version,
        )

    def restore(self) -> SwarmState:
        return SwarmState.from_json_dict(self.state_snapshot)


__all__ = ["SwarmState", "SwarmCheckpoint"]
