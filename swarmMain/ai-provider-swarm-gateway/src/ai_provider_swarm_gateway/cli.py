"""
AGENT 28 — Frontend / CLI Agent
Typer CLI: dashboard, gateway, registry commands.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app     = typer.Typer(name="ai-provider-gateway", help="AI Provider Swarm Gateway CLI")
console = Console()


@app.command("dashboard")
def cmd_dashboard(
    links: bool = typer.Option(False, "--links", help="Show links table instead of quota table"),
) -> None:
    """Show interactive provider dashboard with free-tier info."""
    from .dashboard.app import show_provider_links, show_provider_table
    if links:
        show_provider_links()
    else:
        show_provider_table()


@app.command("list-free")
def cmd_list_free() -> None:
    """List only providers with confirmed free API access."""
    from .registry.loader import get_free_api_providers
    providers = get_free_api_providers()
    console.print(f"\n[bold green]Providers with confirmed free API access ({len(providers)} found):[/bold green]")
    for p in providers:
        console.print(f"  • [cyan]{p.provider_name}[/cyan] — {p.quota.free_daily_usage or p.quota.free_monthly_usage or 'see notes'}")
    console.print()


@app.command("run")
def cmd_run(
    prompt: str = typer.Argument(..., help="Prompt to send to the gateway"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Preferred provider ID"),
    allow_unknown: bool = typer.Option(False, "--allow-unknown", help="Allow routing to unknown-quota providers"),
) -> None:
    """Run a prompt through the AI provider gateway (uses mock by default)."""
    from .graph.builder import build_gateway_graph
    from .models.state import GatewayState

    state = GatewayState(
        user_prompt=prompt,
        preferred_provider_id=provider,
        allow_unknown_quota=allow_unknown,
    )
    graph = build_gateway_graph()
    result = graph.invoke(state.to_json_dict())
    final = GatewayState.from_json_dict(result)

    if final.provider_response and final.provider_response.content:
        console.print(f"\n[bold green]Response from {final.provider_response.provider_id}:[/bold green]")
        console.print(final.provider_response.content)
    elif final.provider_response and final.provider_response.error:
        console.print(f"\n[bold red]Error:[/bold red] {final.provider_response.error}")
    else:
        console.print("\n[bold red]No response received.[/bold red]")

    if final.errors:
        console.print(f"\n[yellow]Errors:[/yellow] {final.errors}")
    if final.routing_decision:
        console.print(f"\n[dim]Selected: {final.routing_decision.selected_provider_id} | Reason: {final.routing_decision.reason}[/dim]")


@app.command("quota")
def cmd_quota() -> None:
    """Show current local quota usage."""
    from .quota.tracker import QuotaTracker
    tracker = QuotaTracker()
    usage = tracker.all_usage()
    if not usage:
        console.print("[dim]No quota usage recorded yet.[/dim]")
        return
    from rich.table import Table
    table = Table(title="Local Quota Usage")
    table.add_column("Provider + Window")
    table.add_column("Requests Used")
    table.add_column("Tokens Used")
    for key, u in usage.items():
        table.add_row(key, str(u.used_requests), str(u.used_tokens))
    console.print(table)


if __name__ == "__main__":
    app()
