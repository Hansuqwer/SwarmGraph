"""Optional MCP toolbox helpers for SwarmGraph.

The CLI group is importable with the base gateway install. The ``serve`` command
is intentionally lazy: it only imports the optional MCP SDK when an operator
explicitly starts the stdio MCP server.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 - optional local Flutter analyzer command, no shell use.
from pathlib import Path
from typing import Any

import typer

from .mcp_allowlist import WorkspaceNotAllowed, enforce_allowed_path
from .observability import increment_counter, log_event

app = typer.Typer(
    name="mcp-toolbox",
    help="Optional MCP toolbox helpers for SwarmGraph + Flutter workflows.",
    no_args_is_help=True,
)

_TOOLBOX_TOOLS: tuple[dict[str, str], ...] = (
    {
        "name": "toolbox_manifest",
        "description": "Return the SwarmGraph MCP toolbox manifest.",
    },
    {
        "name": "flutter_project_summary",
        "description": "Summarize pubspec, lib/test presence, and Flutter project shape.",
    },
    {
        "name": "run_flutter_analyze",
        "description": "Run flutter analyze in a project root and return stdout/stderr/exit code.",
    },
)


def toolbox_manifest() -> dict[str, Any]:
    """Return a JSON-serializable manifest for MCP clients and operators."""
    return {
        "name": "swarmgraph-mcptoolbox",
        "version": "0.1.0",
        "transport": "stdio",
        "install_extra": "ai-provider-swarm-gateway[flutter]",
        "compatibility_extras": ["mcp-toolbox"],
        "tools": list(_TOOLBOX_TOOLS),
    }


def flutter_project_summary(root: str = ".") -> dict[str, Any]:
    """Return a safe, read-only Flutter project summary."""
    try:
        project_root = enforce_allowed_path(root)
    except WorkspaceNotAllowed as exc:
        increment_counter("mcp_tool_rejects_total")
        log_event(
            "mcp.tool.reject", level="warning", tool="flutter_project_summary", reason=str(exc)
        )
        return {"ok": False, "error": "workspace_not_allowed", "detail": str(exc)}
    pubspec = project_root / "pubspec.yaml"
    lib_dir = project_root / "lib"
    test_dir = project_root / "test"
    return {
        "root": str(project_root),
        "pubspec_exists": pubspec.exists(),
        "lib_exists": lib_dir.is_dir(),
        "test_exists": test_dir.is_dir(),
        "dart_files": len(list(lib_dir.rglob("*.dart"))) if lib_dir.is_dir() else 0,
        "test_files": len(list(test_dir.rglob("*.dart"))) if test_dir.is_dir() else 0,
    }


def run_flutter_analyze(root: str = ".") -> dict[str, Any]:
    """Run ``flutter analyze`` without shell expansion."""
    try:
        project_root = enforce_allowed_path(root)
    except WorkspaceNotAllowed as exc:
        increment_counter("mcp_tool_rejects_total")
        log_event("mcp.tool.reject", level="warning", tool="run_flutter_analyze", reason=str(exc))
        return {
            "ok": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": str(exc),
            "error": "workspace_not_allowed",
        }
    flutter = shutil.which("flutter")
    if flutter is None:
        return {"ok": False, "exit_code": 127, "stdout": "", "stderr": "flutter not found"}
    proc = subprocess.run(  # noqa: S603 # nosec B603 - fixed executable path, no shell.
        [flutter, "analyze"],
        cwd=str(project_root),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
    }


@app.command("tools")
def tools(json_output: bool = typer.Option(False, "--json")) -> None:
    """List toolbox tools without starting an MCP server."""
    payload = toolbox_manifest()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo("SwarmGraph MCP toolbox tools:")
        for tool in payload["tools"]:
            typer.echo(f"- {tool['name']}: {tool['description']}")


@app.command("doctor")
def doctor(json_output: bool = typer.Option(False, "--json")) -> None:
    """Check local prerequisites for Flutter/MCP development."""
    try:
        import mcp  # type: ignore[import-not-found]  # noqa: F401

        mcp_installed = True
    except Exception:
        mcp_installed = False
    payload = {
        "mcp_sdk_installed": mcp_installed,
        "dart": shutil.which("dart") or "",
        "flutter": shutil.which("flutter") or "",
        "swarmgraph_cli": shutil.which("ai-provider-gateway") or shutil.which("swarmgraph") or "",
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            typer.echo(f"{key}: {value or 'missing'}")


@app.command("config")
def config(
    include_dart: bool = typer.Option(True, "--dart/--no-dart"),
    include_swarmgraph: bool = typer.Option(True, "--swarmgraph/--no-swarmgraph"),
) -> None:
    """Print a generic MCP client config snippet."""
    servers: dict[str, Any] = {}
    if include_dart:
        servers["dart"] = {"command": "dart", "args": ["mcp-server"]}
    if include_swarmgraph:
        servers["swarmgraph-mcptoolbox"] = {
            "command": "ai-provider-gateway",
            "args": ["mcp-toolbox", "serve"],
            "env": {},
        }
    print(json.dumps({"mcpServers": servers}, indent=2, sort_keys=True))


@app.command("serve")
def serve() -> None:
    """Start the optional stdio MCP server.

    Requires the optional MCP SDK. Install with:
    ``pip install ai-provider-swarm-gateway[flutter]``.
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - optional dependency path
        raise typer.BadParameter(
            "MCP SDK is not installed; install ai-provider-swarm-gateway[flutter] "
            "(or legacy [mcp-toolbox])"
        ) from exc

    mcp = FastMCP("swarmgraph-mcptoolbox")
    mcp.tool()(toolbox_manifest)
    mcp.tool()(flutter_project_summary)
    mcp.tool()(run_flutter_analyze)
    mcp.run()


__all__ = [
    "app",
    "toolbox_manifest",
    "flutter_project_summary",
    "run_flutter_analyze",
]
