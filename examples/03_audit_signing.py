from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from swarm_shared.audit import AuditChain, load_jsonl_chain, verify_chain


def main() -> None:
    secret = os.environ.get("HIVE_SWARM_AUDIT_SECRET", "demo-secret-not-for-production")
    with TemporaryDirectory() as td:
        path = Path(td) / "audit.jsonl"
        chain = AuditChain(swarm_id="demo", secret=secret, jsonl_path=path)
        chain.append(kind="worker_result", payload={"agent": "coder", "success": True})
        chain.append(kind="consensus_result", payload={"agreement": 1.0})
        records = load_jsonl_chain(path)
        print(f"verified={verify_chain(records, secret=secret)} path={path}")


if __name__ == "__main__":
    main()
