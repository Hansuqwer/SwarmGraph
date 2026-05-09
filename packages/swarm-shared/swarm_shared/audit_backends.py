"""Optional audit persistence backends.

Core audit verification stays in :mod:`swarm_shared.audit` and remains
order-sensitive. Backends only load or append records.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Protocol

from .audit import AuditRecord


class AuditBackend(Protocol):
    def append(self, record: AuditRecord) -> None: ...
    def load(self, swarm_id: str) -> list[AuditRecord]: ...


class MissingAuditBackendDependency(RuntimeError):
    """Raised when an optional backend dependency is not installed."""


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
        day = datetime.fromtimestamp(record.timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
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

            kwargs: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": key,
                "Body": (current + line).encode("utf-8"),
            }
            if etag:
                kwargs["IfMatch"] = etag
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

    def load(self, swarm_id: str) -> list[AuditRecord]:
        if not swarm_id:
            raise ValueError("swarm_id is required")
        client = self._get_client()
        keys: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{self.prefix}/"):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", ""))
                if key.endswith(f"/{swarm_id}.jsonl"):
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


__all__ = ["AuditBackend", "MissingAuditBackendDependency", "S3AuditBackend"]
