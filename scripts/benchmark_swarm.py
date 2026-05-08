from __future__ import annotations

import subprocess
import sys
import time


def main() -> None:
    cmd = [
        sys.executable,
        "examples/01_smoke_stub_mode.py",
    ]
    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    elapsed = time.perf_counter() - start
    print(f"stub smoke elapsed={elapsed:.3f}s")


if __name__ == "__main__":
    main()
