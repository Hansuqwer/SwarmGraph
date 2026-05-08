"""v8 surgical additions to dispatch.py — apply manually.

Rather than ship a full rewrite of dispatch.py (~600 LoC), this module
documents the focused changes you should apply to your local
swarm/llm/dispatch.py.

WHY surgical: the v6/v7 patches that wholesale-replaced dispatch.py
introduced regressions you had to re-apply. v8 is small enough to do as
inline edits guided by this module.

WHAT to change:

  1. ADD `StreamingHITLInterrupt` exception class at module top
  2. ADD `_StreamingGuard` helper class (per-chunk regex + length check)
  3. MODIFY `GatewayDispatcher.dispatch_stream` to wrap chunks through
     the guard
  4. EXPORT `StreamingHITLInterrupt` in __all__

After applying, swarm/llm/__init__.py also needs:
    from .dispatch import StreamingHITLInterrupt
    __all__ += ["StreamingHITLInterrupt"]

The four code blocks to insert/replace are below as triple-quoted strings,
each labeled and self-contained.
"""

# ─── Block 1: ADD near the top of dispatch.py, after WorkerLLMError ────

BLOCK_1_EXCEPTION = '''
class StreamingHITLInterrupt(RuntimeError):
    """Raised by GatewayDispatcher.dispatch_stream when a streaming guard fires.

    Attributes:
      reason: short string identifying the trigger ('pattern_match' or 'max_chars_exceeded')
      partial_text: the accumulated streamed output up to the trigger
      matched_pattern: regex source if reason == 'pattern_match'; empty otherwise
      char_count: len(partial_text)

    Caller (worker_node) catches this and either:
      a. converts to a failed WorkerResult (default streaming_hitl_action_default='abort')
      b. continues the stream (when 'continue')
      c. accepts the partial text as the final output (when 'accept_partial')
    """

    def __init__(
        self,
        reason: str,
        partial_text: str,
        *,
        matched_pattern: str = "",
    ) -> None:
        super().__init__(f"streaming HITL: {reason}")
        self.reason = reason
        self.partial_text = partial_text
        self.matched_pattern = matched_pattern
        self.char_count = len(partial_text)
'''

# ─── Block 2: ADD before GatewayDispatcher class definition ─────────────

BLOCK_2_GUARD = '''
import re as _re_v8


class _StreamingGuard:
    """Per-chunk guard for streaming dispatch.

    Cheap-first check order:
      1. Length cap (single int comparison)
      2. Pattern check (only every N chunks; throttled)

    Raises StreamingHITLInterrupt on first trigger. Returns silently otherwise.
    """

    def __init__(
        self,
        *,
        guard_patterns: list[str] | None = None,
        max_output_chars: int = 16384,
        check_every_n_chunks: int = 4,
    ) -> None:
        self.compiled_patterns = [
            _re_v8.compile(p) for p in (guard_patterns or [])
        ]
        self.max_output_chars = int(max_output_chars)
        self.check_every_n_chunks = max(1, int(check_every_n_chunks))
        self._chunks_since_check = 0

    def check(self, accumulated_text: str, chunk_index: int) -> None:
        """Inspect the accumulated text. Raise if a guard fires."""
        # Length cap is cheap — check every chunk
        if len(accumulated_text) > self.max_output_chars:
            raise StreamingHITLInterrupt(
                "max_chars_exceeded",
                accumulated_text,
            )

        # Throttle pattern checks
        self._chunks_since_check += 1
        if self._chunks_since_check < self.check_every_n_chunks:
            return
        self._chunks_since_check = 0

        for pat in self.compiled_patterns:
            m = pat.search(accumulated_text)
            if m is not None:
                raise StreamingHITLInterrupt(
                    "pattern_match",
                    accumulated_text,
                    matched_pattern=pat.pattern,
                )
'''

# ─── Block 3: REPLACE the body of GatewayDispatcher.dispatch_stream ────

BLOCK_3_DISPATCH_STREAM = '''
    def dispatch_stream(self, role, task_description, context=None):
        """v8: per-chunk guards via _StreamingGuard.

        Reads guard config from settings via task_context (workers receive
        the queen-forwarded llm_settings dict in shared_context).
        """
        provider_id = self._provider_for_role(role)
        model_id = self._model_for_role(role)

        try:
            adapter = self._ensure_adapter(provider_id)
        except WorkerLLMError:
            raise
        except Exception as e:
            raise WorkerLLMError(f"could not load adapter {provider_id!r}: {e}") from e

        if not getattr(adapter, "is_configured", lambda: True)():
            raise WorkerLLMError(f"adapter {provider_id!r} is not configured")

        # v8: build the streaming guard from queen-forwarded settings
        guard_patterns: list[str] = []
        max_output_chars = 16384
        check_every_n_chunks = 4
        if context:
            shared = context.get("shared_context") or {}
            ls = shared.get("llm_settings") or {}
            guard_patterns = list(ls.get("streaming_guard_patterns") or [])
            max_output_chars = int(ls.get("streaming_max_output_chars") or 16384)
            check_every_n_chunks = int(ls.get("streaming_guard_check_every_n_chunks") or 4)
        guard = _StreamingGuard(
            guard_patterns=guard_patterns,
            max_output_chars=max_output_chars,
            check_every_n_chunks=check_every_n_chunks,
        )

        chat_stream = getattr(adapter, "chat_stream", None)
        if not callable(chat_stream):
            full = self.dispatch_full(role, task_description, context)
            yield StreamChunk(
                delta=full.text, text=full.text, index=0,
                done=True, finish_reason=full.finish_reason or "stop",
            )
            return

        system_prompt = get_system_prompt(role)
        user_prompt = _build_user_prompt(
            task_description, context,
            include_retrieved_patterns=self.include_retrieved_patterns,
            include_objective=self.include_objective,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs = {"max_tokens": self.max_tokens, "temperature": self.temperature}
        if model_id:
            kwargs["model"] = model_id

        try:
            stream = chat_stream(messages=messages, **kwargs)
        except TypeError:
            try:
                stream = chat_stream(messages=messages, **{k: v for k, v in kwargs.items() if k != "model"})
            except Exception as e:
                raise WorkerLLMError(f"chat_stream call failed: {e}") from e
        except Exception as e:
            raise WorkerLLMError(f"chat_stream call failed: {e}") from e

        accumulated = ""
        index = 0
        last_finish = ""
        try:
            for raw in stream:
                delta, finish = _normalise_stream_chunk(raw)
                if delta:
                    accumulated += delta
                last_finish = finish or last_finish

                # v8: guard check (raises StreamingHITLInterrupt on trigger)
                guard.check(accumulated, index)

                yield StreamChunk(
                    delta=delta, text=accumulated, index=index,
                    done=False, finish_reason=last_finish,
                )
                index += 1
        except StreamingHITLInterrupt:
            # Re-raise; worker_node catches it
            raise
        except Exception as e:
            raise WorkerLLMError(f"chat_stream iteration raised: {e}") from e

        yield StreamChunk(
            delta="", text=accumulated, index=index,
            done=True, finish_reason=last_finish or "stop",
        )
'''

# ─── Block 4: ADD to __all__ at the bottom of dispatch.py ──────────────

BLOCK_4_EXPORT = '''
# (extend the existing __all__ with this entry)
"StreamingHITLInterrupt",
'''

INSTRUCTIONS = """
APPLY MANUALLY (5-min surgical edit):

1. Open swarm/llm/dispatch.py
2. After the `class WorkerLLMError(RuntimeError):` definition, paste BLOCK_1_EXCEPTION
3. Just above `class GatewayDispatcher:`, paste BLOCK_2_GUARD
4. Inside GatewayDispatcher, REPLACE the existing dispatch_stream method
   with BLOCK_3_DISPATCH_STREAM (yes, the entire method body)
5. Add "StreamingHITLInterrupt" to the existing __all__ at the bottom
6. Open swarm/llm/__init__.py
7. Add `StreamingHITLInterrupt` to the imports from .dispatch and to __all__

Then verify:
    pytest hive-swarm/tests/test_v8_streaming_hitl.py -q

If any test fails because of an import error, the most likely cause is
that __init__.py is missing the export.
"""

print(INSTRUCTIONS)
