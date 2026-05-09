"""Workspace allowlist for path-based MCP toolbox calls."""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "AI_PROVIDER_GATEWAY_MCP_ALLOWED_ROOTS"


class WorkspaceNotAllowed(PermissionError):
    """Raised when an MCP path is outside configured workspace roots."""


def _split_roots(raw: str) -> list[str]:
    roots: list[str] = []
    for comma_part in raw.split(","):
        cleaned = comma_part.strip()
        if cleaned:
            roots.append(cleaned)
    return roots


def allowed_roots() -> tuple[Path, ...]:
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        return ()
    return tuple(Path(item).expanduser().resolve() for item in _split_roots(raw))


def enforce_allowed_path(path: str | os.PathLike[str]) -> Path:
    """Resolve path and require it to be inside one configured root.

    Fail-closed: empty/unset AI_PROVIDER_GATEWAY_MCP_ALLOWED_ROOTS rejects all
    path-based MCP tools.
    """
    resolved = Path(path).expanduser().resolve()
    roots = allowed_roots()
    if not roots:
        raise WorkspaceNotAllowed(f"{ENV_VAR} is not configured")
    for root in roots:
        if resolved == root:
            return resolved
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved
    raise WorkspaceNotAllowed(f"path {resolved} is outside allowed MCP roots")


__all__ = ["ENV_VAR", "WorkspaceNotAllowed", "allowed_roots", "enforce_allowed_path"]
