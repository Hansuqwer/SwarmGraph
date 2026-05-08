"""Per-provider, per-model pricing tables (May 2026 baseline).

Source: research/2026_models_baseline.md + provider public pricing pages
as of 2026-05-07. Prices in USD per 1,000 tokens.

Public API:
  - PricingEntry          (frozen dataclass)
  - PricingTable          (the registry; loadable from JSON)
  - DEFAULT_PRICING_TABLE (shipped May-2026 rates)
  - estimate_cost(model_id, input_tokens, output_tokens, table=None) -> float|None

Lookup is best-effort: returns None on miss rather than raising. This means
free providers (9router, mock, ollama) and unknown model ids both surface as
"unpriced" — caller decides how to display (we render "—" in CLI).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class PricingEntry:
    """USD per 1,000 tokens. Negative = free (sentinel)."""
    model_id: str
    input_per_1k: float
    output_per_1k: float
    notes: str = ""

    @property
    def is_free(self) -> bool:
        return self.input_per_1k <= 0 and self.output_per_1k <= 0


@dataclass(frozen=True)
class PricingTable:
    """Registry of model_id → PricingEntry.

    Lookup tries:
      1. Exact match on model_id
      2. Match after stripping a `:free` / `:beta` / `:preview` suffix
      3. Prefix match on the part before the first `/` (provider hint)
      4. Returns None
    """
    entries: dict[str, PricingEntry] = field(default_factory=dict)

    def lookup(self, model_id: str) -> Optional[PricingEntry]:
        if not model_id:
            return None
        # 1. exact
        if model_id in self.entries:
            return self.entries[model_id]
        # 2. strip common suffixes
        base = re.sub(r":(?:free|beta|preview|trial)$", "", model_id)
        if base != model_id and base in self.entries:
            return self.entries[base]
        # 3. provider/* match — for 9router-style provider/model ids, try:
        #    "stepfun/step-3.5-flash" → "stepfun/*"
        if "/" in model_id:
            provider_glob = model_id.split("/", 1)[0] + "/*"
            if provider_glob in self.entries:
                return self.entries[provider_glob]
        return None

    def estimate_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Optional[float]:
        entry = self.lookup(model_id)
        if entry is None:
            return None
        if entry.is_free:
            return 0.0
        cost = (
            entry.input_per_1k * (input_tokens / 1000.0)
            + entry.output_per_1k * (output_tokens / 1000.0)
        )
        return round(cost, 6)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PricingTable":
        entries = {}
        for k, v in (data.get("entries") or data).items():
            if isinstance(v, dict):
                entries[k] = PricingEntry(
                    model_id=k,
                    input_per_1k=float(v.get("input_per_1k", 0)),
                    output_per_1k=float(v.get("output_per_1k", 0)),
                    notes=str(v.get("notes", "")),
                )
        return cls(entries=entries)

    @classmethod
    def from_json_file(cls, path: Path) -> "PricingTable":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ── May-2026 default pricing ──────────────────────────────────────────────

# Free / local providers
_FREE: list[PricingEntry] = [
    PricingEntry("kc/kilo-auto/free", 0.0, 0.0, "9router free tier"),
    PricingEntry("9router/*", 0.0, 0.0, "9router routes through free providers"),
    PricingEntry("mock", 0.0, 0.0, "deterministic test adapter"),
    PricingEntry("stub:deterministic", 0.0, 0.0, "hive-swarm stub mode"),
    PricingEntry("ollama_local", 0.0, 0.0, "local inference"),
    PricingEntry("ollama/*", 0.0, 0.0, "local inference (any model)"),
    PricingEntry("stepfun/step-3.5-flash", 0.0, 0.0, "free tier via 9router"),
    PricingEntry("stepfun/*", 0.0, 0.0, "stepfun free tier"),
]

# Anthropic — May 2026 (per platform docs)
_ANTHROPIC: list[PricingEntry] = [
    PricingEntry("claude-opus-4-7", 5.0 / 1000, 25.0 / 1000, "$5 in / $25 out per MTok"),
    PricingEntry("anthropic/claude-opus-4-7", 5.0 / 1000, 25.0 / 1000, ""),
    PricingEntry("claude-opus-4-6", 5.0 / 1000, 25.0 / 1000, ""),
    PricingEntry("anthropic/claude-opus-4-6", 5.0 / 1000, 25.0 / 1000, ""),
    PricingEntry("claude-sonnet-4-6", 3.0 / 1000, 15.0 / 1000, "$3 in / $15 out per MTok"),
    PricingEntry("anthropic/claude-sonnet-4-6", 3.0 / 1000, 15.0 / 1000, ""),
    PricingEntry("claude-haiku-4-5", 1.0 / 1000, 5.0 / 1000, "$1 in / $5 out per MTok"),
    PricingEntry("anthropic/claude-haiku-4-5", 1.0 / 1000, 5.0 / 1000, ""),
]

# OpenAI — approximate May 2026 (verify before billing)
_OPENAI: list[PricingEntry] = [
    PricingEntry("gpt-4o-mini", 0.15 / 1000, 0.60 / 1000, "approx; verify"),
    PricingEntry("openai/gpt-4o-mini", 0.15 / 1000, 0.60 / 1000, ""),
    PricingEntry("gpt-4o", 5.0 / 1000, 15.0 / 1000, "approx; verify"),
    PricingEntry("openai/gpt-4o", 5.0 / 1000, 15.0 / 1000, ""),
]

# Other named providers — token costs negligible for free tiers
_OTHER: list[PricingEntry] = [
    PricingEntry("groq/*", 0.0, 0.0, "free tier; usage-cap'd"),
    PricingEntry("deepseek/*", 0.0, 0.0, "free tier; usage-cap'd"),
    PricingEntry("zhipu_glm/*", 0.0, 0.0, "free tier"),
    PricingEntry("moonshot_kimi/*", 0.0, 0.0, "free tier"),
    PricingEntry("qwen/*", 0.0, 0.0, "free tier"),
    PricingEntry("openrouter/*", -1.0, -1.0, "openrouter prices vary per route; lookup miss expected"),
]


def _build_default_table() -> PricingTable:
    entries: dict[str, PricingEntry] = {}
    for batch in (_FREE, _ANTHROPIC, _OPENAI, _OTHER):
        for e in batch:
            # Treat negative-sentinel entries as "unknown" — leave out of table.
            if e.input_per_1k < 0 or e.output_per_1k < 0:
                continue
            entries[e.model_id] = e
    return PricingTable(entries=entries)


DEFAULT_PRICING_TABLE = _build_default_table()


def estimate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    table: Optional[PricingTable] = None,
) -> Optional[float]:
    """Convenience wrapper around the default table."""
    return (table or DEFAULT_PRICING_TABLE).estimate_cost(
        model_id, input_tokens, output_tokens
    )


__all__ = [
    "PricingEntry",
    "PricingTable",
    "DEFAULT_PRICING_TABLE",
    "estimate_cost",
]
