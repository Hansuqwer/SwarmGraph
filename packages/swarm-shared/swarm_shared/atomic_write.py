"""Atomic write helpers (F-W6A consolidation; replaces 2 duplications).

Atomicity: write to a tempfile in the same directory, then os.replace().
On POSIX: os.replace is atomic for files on the same filesystem.
On Windows: os.replace is atomic since Python 3.3 (uses MoveFileEx with
MOVEFILE_REPLACE_EXISTING).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically write `content` to `path`.

    Crash-safe: on any failure, the original file at `path` is preserved
    and the partial tempfile is unlinked.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, str(target))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_json(
    path: Path,
    data: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    default: Any = str,
) -> None:
    """Atomically serialize `data` as JSON to `path`."""
    serialised = json.dumps(data, indent=indent, sort_keys=sort_keys, default=default)
    atomic_write_text(path, serialised)
