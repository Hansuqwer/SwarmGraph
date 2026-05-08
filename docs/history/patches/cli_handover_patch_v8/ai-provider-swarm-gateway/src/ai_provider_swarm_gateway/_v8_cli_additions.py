"""v8 surgical additions to ai-provider-swarm-gateway/.../cli.py.

Same pattern as the dispatch.py additions: rather than wholesale-rewrite
the 600-LoC CLI (which has caused regressions in v6/v7), this module
documents the focused additions.

Two changes:

  1. ADD a new `audit verify` subcommand
  2. ADD a `_streaming_hitl_prompt()` helper for interactive stream-HITL
     resume (paired with consensus HITL — same single-use token discipline)

The new subcommand is a separate Typer app, so it can be registered with
one line:
    audit_app = ...   # (defined in this file)
    app.add_typer(audit_app)
"""

# ─── Block 1: ADD near the top of cli.py, after providers_app definition ─

BLOCK_1_TYPER_APP = '''
audit_app = typer.Typer(
    name="audit",
    help="Verify HMAC-SHA256-signed audit logs.",
    no_args_is_help=True,
)
app.add_typer(audit_app)
'''

# ─── Block 2: ADD as a new top-level command function ───────────────────

BLOCK_2_VERIFY_COMMAND = '''
@audit_app.command("verify")
def audit_verify(
    log_path: Path = typer.Argument(
        ..., exists=True, file_okay=True, dir_okay=False,
        help="Path to the JSONL audit log to verify.",
    ),
    secret_env: str = typer.Option(
        "HIVE_SWARM_AUDIT_SECRET", "--secret-env",
        help="Env var holding the HMAC secret used to sign the log.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify an audit log's HMAC signatures + chain integrity.

    Exit codes:
      0 = clean (every record verifies, chain unbroken)
      1 = secret missing
      2 = log file malformed (not valid JSONL)
      3 = chain broken (insertion / deletion / reorder / tampered field)
    """
    import os as _os_v8
    try:
        from swarm_shared.audit import (
            AuditChainBroken,
            load_jsonl_chain,
            verify_chain,
        )
    except ImportError as e:
        _err(f"swarm_shared.audit not importable: {e}")
        raise typer.Exit(1)

    secret = _os_v8.environ.get(secret_env)
    if not secret:
        _err(f"env var {secret_env!r} unset; cannot verify signatures")
        raise typer.Exit(1)

    try:
        records = load_jsonl_chain(log_path)
    except Exception as e:
        _err(f"audit log malformed: {e}")
        raise typer.Exit(2)

    if not records:
        if json_output:
            print(json.dumps({"verified": 0, "ok": True, "reason": "empty log"}))
        else:
            _print("[empty audit log]")
        return

    try:
        count = verify_chain(records, secret=secret.encode("utf-8"))
    except AuditChainBroken as e:
        if json_output:
            print(json.dumps({
                "verified": 0, "ok": False,
                "total_records": len(records),
                "error": str(e),
            }))
        else:
            _err(f"❌ chain broken: {e}")
        raise typer.Exit(3)

    # Summary by kind
    by_kind: dict[str, int] = {}
    for r in records:
        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1

    if json_output:
        print(json.dumps({
            "verified": count, "ok": True,
            "total_records": len(records),
            "swarm_ids": sorted({r.swarm_id for r in records}),
            "by_kind": by_kind,
        }, indent=2))
    else:
        if _HAS_RICH and _console:
            t = Table(title=f"Audit log verified: {log_path}")
            t.add_column("Kind"); t.add_column("Count", justify="right")
            for kind, n in sorted(by_kind.items()):
                t.add_row(kind, str(n))
            _console.print(t)
            _console.print(f"[green]✅ {count} records verified, chain intact[/green]")
        else:
            print(f"✅ verified {count} records")
            for kind, n in sorted(by_kind.items()):
                print(f"  {kind:25s} {n}")
'''

# ─── Block 3: ADD as a helper near _interactive_hitl_prompt ─────────────

BLOCK_3_STREAM_HITL_PROMPT = '''
def _streaming_hitl_prompt(
    swarm_id: str,
    *,
    reason: str,
    matched_pattern: str,
    partial_text: str,
    decision_token: str,
) -> dict | None:
    """Prompt the operator on a streaming HITL trigger.

    Returns:
      {"action": "abort" | "continue" | "accept_partial",
       "reviewer_id": "<resolved>",
       "decision_token": "<echoed>"}
    or None if response can't be parsed (caller treats as abort).

    Same single-use discipline as consensus HITL: token is echoed verbatim.
    """
    if _HAS_RICH and _console:
        _console.rule(f"[bold yellow]Streaming HITL[/bold yellow] swarm={swarm_id}")
        _console.print(f"[dim]reason[/dim] {reason}  [dim]token[/dim] {decision_token[:8]}…")
        if matched_pattern:
            _console.print(f"[dim]matched_pattern[/dim] {matched_pattern!r}")
        _console.print(Panel(_rich_escape(partial_text[:2000]),
                              title=f"Partial output ({len(partial_text)} chars)"))
    else:
        print(f"# Streaming HITL — swarm={swarm_id}")
        print(f"# reason={reason}  token={decision_token[:8]}…")
        if matched_pattern:
            print(f"# matched_pattern={matched_pattern!r}")
        print(f"# partial output ({len(partial_text)} chars):")
        print(partial_text[:2000])

    reviewer_id = (
        os.environ.get("AI_PROVIDER_GATEWAY_REVIEWER_ID")
        or os.environ.get("USER")
        or "cli"
    )

    try:
        choice = typer.prompt(
            "Action? (a=abort / c=continue / p=accept_partial)",
            default="a",
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if choice in ("a", "abort"):
        action = "abort"
    elif choice in ("c", "continue"):
        action = "continue"
    elif choice in ("p", "accept_partial", "partial"):
        action = "accept_partial"
    else:
        return None

    return {
        "action": action,
        "reviewer_id": reviewer_id,
        "decision_token": decision_token,
    }
'''

INSTRUCTIONS = """
APPLY MANUALLY (5-min surgical edit):

1. Open ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py
2. Near the top, after `providers_app = typer.Typer(...)` add BLOCK_1_TYPER_APP
   (registers a new `audit` subcommand group)
3. As a new top-level function (anywhere in the file before main()),
   paste BLOCK_2_VERIFY_COMMAND
4. Near _interactive_hitl_prompt (the consensus HITL helper), paste
   BLOCK_3_STREAM_HITL_PROMPT — for future use when wiring streaming
   HITL into the swarm CLI command (left as a v9 followup; v8 ships the
   helper but doesn't yet thread it through the swarm subcommand)

Then verify:
    pytest ai-provider-swarm-gateway/tests/test_v8_audit_cli.py -q

If `audit verify` exits with code 1 even though the env var is set, check
that the env var is being inherited into the test subprocess (Typer's
CliRunner does inherit by default).
"""

print(INSTRUCTIONS)
