"""Optional audit persistence backends.

Core audit verification stays in :mod:`swarm_shared.audit` and remains
order-sensitive. Backends only load or append records.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from .audit import AuditRecord, append_jsonl, load_jsonl_chain
from .audit import _assert_append_boundary as assert_append_boundary


class AuditBackend(Protocol):
    def append(self, record: AuditRecord) -> None: ...
    def load(
        self,
        swarm_id: str,
        *,
        tenant_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[AuditRecord]: ...


class MissingAuditBackendDependency(RuntimeError):
    """Raised when an optional backend dependency is not installed."""


def _parse_day(value: str | None, *, name: str) -> date | None:
    if value is None:
        return None
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError(f"{name} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD") from exc


def _record_day(record: AuditRecord) -> date:
    return datetime.fromtimestamp(record.timestamp, tz=UTC).date()


def _filter_records_by_date(
    records: list[AuditRecord],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[AuditRecord]:
    start = _parse_day(start_date, name="start_date")
    end = _parse_day(end_date, name="end_date")
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must be <= end_date")
    if start is None and end is None:
        return records
    return [
        record
        for record in records
        if (start is None or _record_day(record) >= start)
        and (end is None or _record_day(record) <= end)
    ]


def _date_from_key(key: str, prefix: str) -> date | None:
    rel = key[len(prefix) :].lstrip("/") if key.startswith(prefix) else key
    parts = rel.split("/") if rel else []
    for part in parts:
        try:
            return _parse_day(part, name="partition date")
        except ValueError:
            continue
    return None


class JSONLBackend:
    """Local JSONL audit backend with the same load API as cloud backends."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: AuditRecord) -> None:
        append_jsonl(self.path, record)

    def load(
        self,
        swarm_id: str,
        *,
        tenant_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[AuditRecord]:
        if not swarm_id:
            raise ValueError("swarm_id is required")
        records = [
            record
            for record in load_jsonl_chain(self.path)
            if record.swarm_id == swarm_id
            and (tenant_id is None or record.tenant_id == tenant_id)
        ]
        return _filter_records_by_date(records, start_date=start_date, end_date=end_date)


class S3AuditBackend:
    """S3 JSONL audit backend with date partitions and conditional writes.

    Records are stored as ``<prefix>/YYYY-MM-DD/<swarm_id>.jsonl``. The backend
    uses conditional writes when appending to reduce concurrent writer loss, but
    callers must still verify the loaded chain with pinned head/count values.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "audit",
        region: str | None = None,
        max_workers: int = 8,
        client: Any | None = None,
        legacy_layout: bool = False,
    ) -> None:
        if not bucket or "/" in bucket:
            raise ValueError("bucket must be a non-empty S3 bucket name")
        if max_workers < 1 or max_workers > 32:
            raise ValueError("max_workers must be between 1 and 32")
        self.bucket = bucket
        self.prefix = prefix.strip("/") or "audit"
        self.region = region
        self.max_workers = max_workers
        self._client = client
        self.legacy_layout = legacy_layout

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise MissingAuditBackendDependency(
                "S3 audit backend requires boto3; install the package with the s3 extra"
            ) from exc
        self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def _key_for_record(self, record: AuditRecord) -> str:
        day = datetime.fromtimestamp(record.timestamp, tz=UTC).strftime("%Y-%m-%d")
        if record.tenant_id and not self.legacy_layout:
            return f"{self.prefix}/{record.tenant_id}/{day}/{record.swarm_id}.jsonl"
        return f"{self.prefix}/{day}/{record.swarm_id}.jsonl"

    def _is_not_found(self, error: Exception) -> bool:
        code = getattr(error, "response", {}).get("Error", {}).get("Code", "")
        return code in {"NoSuchKey", "404", "NotFound"}

    def _is_precondition_failed(self, error: Exception) -> bool:
        code = getattr(error, "response", {}).get("Error", {}).get("Code", "")
        return code in {"PreconditionFailed", "412"}

    def append(self, record: AuditRecord) -> None:
        client = self._get_client()
        key = self._key_for_record(record)
        line = record.to_jsonl_line()

        for attempt in range(3):
            current = ""
            etag: str | None = None
            try:
                response = client.get_object(Bucket=self.bucket, Key=key)
                current = response["Body"].read().decode("utf-8")
                etag = response.get("ETag")
            except Exception as exc:  # boto3 raises dynamically generated exceptions
                if not self._is_not_found(exc):
                    raise

            current_records = [
                AuditRecord.model_validate_json(item)
                for item in current.splitlines()
                if item.strip()
            ]
            assert_append_boundary(current_records, record)
            kwargs: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": key,
                "Body": (current + line).encode("utf-8"),
            }
            if etag:
                kwargs["IfMatch"] = etag
            else:
                kwargs["IfNoneMatch"] = "*"
            try:
                client.put_object(**kwargs)
                return
            except Exception as exc:
                if self._is_precondition_failed(exc) and attempt < 2:
                    time.sleep(0.1 * (2**attempt))
                    continue
                raise

    def _load_key(self, key: str) -> list[AuditRecord]:
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._is_not_found(exc):
                return []
            raise
        raw = response["Body"].read().decode("utf-8")
        return [AuditRecord.model_validate_json(line) for line in raw.splitlines() if line.strip()]

    def load(
        self,
        swarm_id: str,
        *,
        tenant_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[AuditRecord]:
        if not swarm_id:
            raise ValueError("swarm_id is required")
        if tenant_id is None and not self.legacy_layout:
            raise ValueError("tenant_id is required for S3 audit load unless legacy_layout=True")
        start = _parse_day(start_date, name="start_date")
        end = _parse_day(end_date, name="end_date")
        if start is not None and end is not None and start > end:
            raise ValueError("start_date must be <= end_date")
        client = self._get_client()
        keys: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        list_prefix = f"{self.prefix}/{tenant_id}/" if tenant_id else f"{self.prefix}/"
        for page in paginator.paginate(Bucket=self.bucket, Prefix=list_prefix):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", ""))
                if not key.endswith(f"/{swarm_id}.jsonl"):
                    continue
                day = _date_from_key(key, self.prefix)
                if start is not None and day is not None and day < start:
                    continue
                if end is not None and day is not None and day > end:
                    continue
                keys.append(key)

        if not keys:
            return []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(keys))) as executor:
            chunks = list(executor.map(self._load_key, sorted(keys)))
        records = [record for chunk in chunks for record in chunk]
        return sorted(records, key=lambda record: record.sequence)

    def restore_archive(self, swarm_id: str, *, days: int = 30, tier: str = "Bulk") -> int:
        """Initiate restore requests for archived objects for ``swarm_id``.

        Returns the number of restore requests submitted.
        """
        if days < 1:
            raise ValueError("days must be >= 1")
        if tier not in {"Bulk", "Standard", "Expedited"}:
            raise ValueError("tier must be Bulk, Standard, or Expedited")
        client = self._get_client()
        count = 0
        paginator = client.get_paginator("list_objects_v2")
        request = {"Days": days, "GlacierJobParameters": {"Tier": tier}}
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{self.prefix}/"):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", ""))
                if key.endswith(f"/{swarm_id}.jsonl"):
                    client.restore_object(Bucket=self.bucket, Key=key, RestoreRequest=request)
                    count += 1
        return count

    def restore_swarm(self, swarm_id: str, *, days: int = 30, tier: str = "Bulk") -> int:
        """Backward-compatible alias for :meth:`restore_archive`."""
        return self.restore_archive(swarm_id, days=days, tier=tier)


__all__ = ["AuditBackend", "MissingAuditBackendDependency", "JSONLBackend", "S3AuditBackend"]
