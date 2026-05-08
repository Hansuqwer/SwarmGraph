from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from ai_provider_swarm_gateway.quota.tracker import QuotaTracker


def main() -> None:
    with TemporaryDirectory() as td:
        path = Path(td) / "quota.json"
        alice = QuotaTracker(path, tenant_id="alice")
        bob = QuotaTracker(path, tenant_id="bob")
        alice.increment("openai", requests=2, tokens=10)
        bob.increment("openai", requests=1, tokens=5)
        print("alice", alice.get_usage("openai"))
        print("bob", bob.get_usage("openai"))


if __name__ == "__main__":
    main()
