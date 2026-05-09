from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timezone

import pytest
from swarm_shared.audit import GENESIS_PREV_HASH, AuditRecord, sign_record, verify_chain
from swarm_shared.audit_backends import JSONLBackend, S3AuditBackend

SECRET = b"test-hmac-secret-not-real"


class _Body:
    def __init__(self, data: str) -> None:
        self._data = data.encode("utf-8")

    def read(self) -> bytes:
        return self._data


class _S3Error(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class _Paginator:
    def __init__(self, client: _FakeS3Client) -> None:
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str):
        contents = [
            {"Key": key}
            for (bucket, key), _value in sorted(self.client.objects.items())
            if bucket == Bucket and key.startswith(Prefix)
        ]
        yield {"Contents": contents}


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[str, str]] = {}
        self.put_attempts: defaultdict[tuple[str, str], int] = defaultdict(int)
        self.fail_first_put: set[tuple[str, str]] = set()
        self.restores: list[dict] = []

    def get_object(self, *, Bucket: str, Key: str):
        try:
            body, etag = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise _S3Error("NoSuchKey") from exc
        return {"Body": _Body(body), "ETag": etag}

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        IfMatch: str | None = None,
        IfNoneMatch: str | None = None,
    ):
        obj_key = (Bucket, Key)
        self.put_attempts[obj_key] += 1
        if obj_key in self.fail_first_put and self.put_attempts[obj_key] == 1:
            raise _S3Error("PreconditionFailed")
        existing = self.objects.get(obj_key)
        if IfMatch is not None and existing is not None and existing[1] != IfMatch:
            raise _S3Error("PreconditionFailed")
        if IfNoneMatch == "*" and existing is not None:
            raise _S3Error("PreconditionFailed")
        self.objects[obj_key] = (Body.decode("utf-8"), f"etag-{self.put_attempts[obj_key]}")
        return {"ETag": self.objects[obj_key][1]}

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        return _Paginator(self)

    def restore_object(self, **kwargs):
        self.restores.append(kwargs)
        return {}


def _record(
    seq: int,
    *,
    swarm_id: str = "s1",
    tenant_id: str = "",
    prev_hash: str = GENESIS_PREV_HASH,
    day: int = 8,
) -> AuditRecord:
    return sign_record(
        kind="worker_result",
        swarm_id=swarm_id,
        sequence=seq,
        payload={"i": seq},
        prev_hash=prev_hash,
        secret=SECRET,
        tenant_id=tenant_id,
        timestamp=datetime(2026, 5, day, tzinfo=UTC).timestamp(),
    )


def test_s3_backend_appends_new_partitioned_object():
    client = _FakeS3Client()
    backend = S3AuditBackend(bucket="audit-bucket", client=client, legacy_layout=True)

    backend.append(_record(0))

    stored = client.objects[("audit-bucket", "audit/2026-05-08/s1.jsonl")][0]
    assert '"swarm_id":"s1"' in stored


def test_s3_backend_retries_on_precondition_failure():
    client = _FakeS3Client()
    key = ("audit-bucket", "audit/2026-05-08/s1.jsonl")
    client.fail_first_put.add(key)
    backend = S3AuditBackend(bucket="audit-bucket", client=client, legacy_layout=True)

    backend.append(_record(0))

    assert client.put_attempts[key] == 2


def test_s3_backend_uses_conditional_create_on_missing_object():
    client = _FakeS3Client()
    backend = S3AuditBackend(bucket="audit-bucket", client=client, legacy_layout=True)

    backend.append(_record(0))

    key = ("audit-bucket", "audit/2026-05-08/s1.jsonl")
    assert client.put_attempts[key] == 1


def test_s3_backend_rejects_when_missing_key_create_races_with_duplicate_genesis():
    class _RacingCreateS3Client(_FakeS3Client):
        def put_object(self, **kwargs):
            obj_key = (kwargs["Bucket"], kwargs["Key"])
            if kwargs.get("IfNoneMatch") == "*" and obj_key not in self.objects:
                self.put_attempts[obj_key] += 1
                existing = _record(0).model_dump_json() + "\n"
                self.objects[obj_key] = (existing, "etag-race")
                raise _S3Error("PreconditionFailed")
            return super().put_object(**kwargs)

    client = _RacingCreateS3Client()
    backend = S3AuditBackend(bucket="audit-bucket", client=client, legacy_layout=True)

    with pytest.raises(Exception, match="append boundary mismatch"):
        backend.append(_record(0))

    key = ("audit-bucket", "audit/2026-05-08/s1.jsonl")
    stored = client.objects[key][0]
    assert stored.count('"sequence":0') == 1
    assert client.put_attempts[key] == 1


def test_s3_backend_rejects_duplicate_genesis_on_existing_object():
    client = _FakeS3Client()
    backend = S3AuditBackend(bucket="audit-bucket", client=client, legacy_layout=True)
    first = _record(0)
    backend.append(first)

    with pytest.raises(Exception, match="append boundary mismatch"):
        backend.append(_record(0))


def test_s3_backend_loads_all_partitions_for_swarm_in_sequence_order():
    client = _FakeS3Client()
    first = _record(0)
    second = _record(1, prev_hash=first.record_hash)
    other = _record(0, swarm_id="other")
    client.objects[("audit-bucket", "audit/2026-05-08/s1.jsonl")] = (
        second.model_dump_json() + "\n",
        "etag-1",
    )
    client.objects[("audit-bucket", "audit/2026-05-07/s1.jsonl")] = (
        first.model_dump_json() + "\n",
        "etag-2",
    )
    client.objects[("audit-bucket", "audit/2026-05-08/other.jsonl")] = (
        other.model_dump_json() + "\n",
        "etag-3",
    )
    backend = S3AuditBackend(bucket="audit-bucket", client=client, legacy_layout=True)

    records = backend.load("s1")

    assert [record.sequence for record in records] == [0, 1]
    assert verify_chain(records, secret=SECRET) == 2


def test_jsonl_backend_loads_by_swarm_and_date_range(tmp_path):
    path = tmp_path / "audit.jsonl"
    backend = JSONLBackend(path)
    first = _record(0, day=7)
    second = _record(1, prev_hash=first.record_hash, day=8)
    other = _record(0, swarm_id="other", day=8)

    backend.append(first)
    backend.append(second)
    backend.append(other)

    assert [record.sequence for record in backend.load("s1")] == [0, 1]
    filtered = backend.load("s1", start_date="2026-05-08", end_date="2026-05-08")
    assert [record.sequence for record in filtered] == [1]
    assert verify_chain(backend.load("s1"), secret=SECRET) == 2


def test_jsonl_backend_load_filters_by_tenant(tmp_path):
    path = tmp_path / "audit.jsonl"
    backend = JSONLBackend(path)
    first = _record(0, tenant_id="tenant-a")
    second = _record(0, tenant_id="tenant-b")

    path.write_text(first.to_jsonl_line() + second.to_jsonl_line(), encoding="utf-8")

    assert [record.tenant_id for record in backend.load("s1")] == ["tenant-a", "tenant-b"]
    assert [record.tenant_id for record in backend.load("s1", tenant_id="tenant-a")] == [
        "tenant-a"
    ]


def test_audit_backend_date_range_rejects_invalid_dates(tmp_path):
    backend = JSONLBackend(tmp_path / "audit.jsonl")
    backend.append(_record(0))

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        backend.load("s1", start_date="20260508")
    with pytest.raises(ValueError, match="<="):
        backend.load("s1", start_date="2026-05-09", end_date="2026-05-08")


def test_s3_backend_load_filters_date_partitions():
    client = _FakeS3Client()
    first = _record(0, day=7)
    second = _record(1, prev_hash=first.record_hash, day=8)
    client.objects[("audit-bucket", "audit/2026-05-07/s1.jsonl")] = (
        first.model_dump_json() + "\n",
        "etag-1",
    )
    client.objects[("audit-bucket", "audit/2026-05-08/s1.jsonl")] = (
        second.model_dump_json() + "\n",
        "etag-2",
    )
    backend = S3AuditBackend(bucket="audit-bucket", client=client, legacy_layout=True)

    records = backend.load("s1", start_date="2026-05-08", end_date="2026-05-08")

    assert [record.sequence for record in records] == [1]


def test_s3_backend_key_includes_tenant_when_set():
    client = _FakeS3Client()
    backend = S3AuditBackend(bucket="audit-bucket", client=client)

    backend.append(_record(0, tenant_id="tenant-a"))

    assert ("audit-bucket", "audit/tenant-a/2026-05-08/s1.jsonl") in client.objects


def test_s3_backend_load_requires_tenant_unless_legacy_layout():
    backend = S3AuditBackend(bucket="audit-bucket", client=_FakeS3Client())

    with pytest.raises(ValueError, match="tenant_id is required"):
        backend.load("s1")


def test_s3_backend_load_lists_only_tenant_prefix():
    client = _FakeS3Client()
    first = _record(0, tenant_id="tenant-a")
    second = _record(0, tenant_id="tenant-b")
    client.objects[("audit-bucket", "audit/tenant-a/2026-05-08/s1.jsonl")] = (
        first.model_dump_json() + "\n",
        "etag-1",
    )
    client.objects[("audit-bucket", "audit/tenant-b/2026-05-08/s1.jsonl")] = (
        second.model_dump_json() + "\n",
        "etag-2",
    )
    backend = S3AuditBackend(bucket="audit-bucket", client=client)

    records = backend.load("s1", tenant_id="tenant-a")

    assert [record.tenant_id for record in records] == ["tenant-a"]


def test_s3_backend_restore_archive_requests_matching_swarm_objects():
    client = _FakeS3Client()
    client.objects[("audit-bucket", "audit/2026-05-07/s1.jsonl")] = ("", "etag-1")
    client.objects[("audit-bucket", "audit/2026-05-08/other.jsonl")] = ("", "etag-2")
    backend = S3AuditBackend(bucket="audit-bucket", client=client)

    count = backend.restore_archive("s1", days=10, tier="Bulk")

    assert count == 1
    assert client.restores[0]["Key"] == "audit/2026-05-07/s1.jsonl"
    assert client.restores[0]["RestoreRequest"]["Days"] == 10


def test_s3_backend_restore_swarm_alias():
    client = _FakeS3Client()
    client.objects[("audit-bucket", "audit/2026-05-07/s1.jsonl")] = ("", "etag-1")
    backend = S3AuditBackend(bucket="audit-bucket", client=client)

    assert backend.restore_swarm("s1", days=7, tier="Standard") == 1
    assert client.restores[0]["RestoreRequest"]["Days"] == 7
    assert client.restores[0]["RestoreRequest"]["GlacierJobParameters"]["Tier"] == "Standard"


def test_s3_backend_rejects_invalid_restore_args():
    backend = S3AuditBackend(bucket="audit-bucket", client=_FakeS3Client())

    with pytest.raises(ValueError, match="days"):
        backend.restore_archive("s1", days=0)
    with pytest.raises(ValueError, match="tier"):
        backend.restore_archive("s1", tier="Fast")
