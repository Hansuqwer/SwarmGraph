import subprocess
import sys
from pathlib import Path

from ai_provider_swarm_gateway.quota.tracker import QuotaTracker


def test_increment_multiprocess_additive_no_loss(tmp_path: Path):
    storage_path = tmp_path / "usage.json"
    workers = 8
    increments = 50
    script = (
        "from pathlib import Path\n"
        "from ai_provider_swarm_gateway.quota.tracker import QuotaTracker\n"
        "tracker = QuotaTracker(storage_path=Path(__import__('sys').argv[1]))\n"
        "for _ in range(int(__import__('sys').argv[2])):\n"
        "    tracker.increment('openai', requests=1, tokens=2)\n"
    )

    procs = [
        subprocess.Popen(  # noqa: S603 - fixed interpreter/script for concurrency regression.
            [sys.executable, "-c", script, str(storage_path), str(increments)]
        )
        for _ in range(workers)
    ]
    for proc in procs:
        assert proc.wait(timeout=30) == 0

    usage = QuotaTracker(storage_path=storage_path).get_usage("openai")
    assert usage.used_requests == workers * increments
    assert usage.used_tokens == workers * increments * 2
