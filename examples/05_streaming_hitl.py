from __future__ import annotations

from swarm.llm.dispatch import GatewayDispatcher, StreamingHITLInterrupt


class FakeAdapter:
    def is_configured(self) -> bool:
        return True

    def chat_stream(self, *, messages, max_tokens, temperature, model=None):
        yield {"delta": "safe ", "finish_reason": ""}
        yield {"delta": "FORBIDDEN ", "finish_reason": ""}


def main() -> None:
    dispatcher = GatewayDispatcher(default_provider="demo", adapter_factory=lambda _p: FakeAdapter())
    context = {
        "shared_context": {
            "llm_settings": {
                "streaming_guard_patterns": ["FORBIDDEN"],
                "streaming_guard_check_every_n_chunks": 1,
            }
        }
    }
    try:
        list(dispatcher.dispatch_stream("coder", "demo", context=context))
    except StreamingHITLInterrupt as exc:
        print(f"interrupted reason={exc.reason} partial={exc.partial_text!r}")


if __name__ == "__main__":
    main()
