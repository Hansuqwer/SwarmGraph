from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from swarm_shared.audit import GENESIS_PREV_HASH, sign_record, verify_chain
from swarm_shared.audit_backends import MissingAuditBackendDependency, S3AuditBackend

pytestmark = pytest.mark.skipif(
    os.environ.get("SWARMGRAPH_LIVE_S3", "").strip().lower() not in {"1", "true", "yes", "on"},
    reason="set SWARMGRAPH_LIVE_S3=1 to run live S3 audit tests",
)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"{name} is required for live S3 audit tests")
    return value


def test_live_s3_audit_append_load_tenant_scoped():
    bucket = _required_env("SWARMGRAPH_LIVE_S3_BUCKET")
    base_prefix = os.environ.get("SWARMGRAPH_LIVE_S3_PREFIX", "swarmgraph-live-tests").strip("/")
    prefix = f"{base_prefix}/{uuid.uuid4().hex}"
    tenant_id = f"tenant-{uuid.uuid4().hex[:12]}"
    swarm_id = f"swarm-{uuid.uuid4().hex[:12]}"
    secret = b"live-s3-test-secret-not-real"
    backend: Any | None = None

    try:
        backend = S3AuditBackend(bucket=bucket, prefix=prefix, client=None)
        first = sign_record(
            kind="worker_result",
            swarm_id=swarm_id,
            tenant_id=tenant_id,
            sequence=0,
            payload={"i": 0},
            prev_hash=GENESIS_PREV_HASH,
            secret=secret,
            timestamp=datetime.now(tz=UTC).timestamp(),
        )
        second = sign_record(
            kind="worker_result",
            swarm_id=swarm_id,
            tenant_id=tenant_id,
            sequence=1,
            payload={"i": 1},
            prev_hash=first.record_hash,
            secret=secret,
            timestamp=datetime.now(tz=UTC).timestamp(),
        )

        backend.append(first)
        backend.append(second)
        records = backend.load(swarm_id, tenant_id=tenant_id)

        assert [record.sequence for record in records] == [0, 1]
        assert {record.tenant_id for record in records} == {tenant_id}
        assert verify_chain(records, secret=secret) == 2
    except MissingAuditBackendDependency:
        pytest.skip("boto3 is required for live S3 audit tests")
    finally:
        try:
            if backend is None:
                raise RuntimeError("backend was not created")
            client = backend._get_client()  # noqa: SLF001 - cleanup for live integration test.
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        except Exception:
            return
