"""Optional Textual dashboard for local SwarmGraph monitoring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .quota.tracker import QuotaTracker

DEFAULT_HISTORY_PATH = Path.home() / ".ai_provider_gateway" / "consensus_history.jsonl"


def load_consensus_history(path: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Load recent consensus records, skipping malformed lines."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records[-limit:]


def build_agreement_plot(history: list[dict[str, Any]]) -> str:
    """Render a text chart for agreement fractions."""
    values = [
        float(item.get("agreement", item.get("agreement_fraction", 0.0)) or 0.0) for item in history
    ]
    if not values:
        values = [0.0]
    try:
        import plotext as plt
    except ImportError:
        rendered = ["Consensus Agreement Trend"]
        for index, value in enumerate(values, start=1):
            bar = "#" * max(1, round(value * 20))
            rendered.append(f"{index:02d} {value:.2f} {bar}")
        return "\n".join(rendered)

    plt.clf()
    plt.theme("dark")
    plt.plot(values, marker="dot", color="magenta")
    plt.title("Consensus Agreement Trend")
    plt.xlabel("recent rounds")
    plt.ylabel("agreement")
    plt.ylim(0, 1.0)
    return plt.build()


def _quota_rows(storage: Path | None) -> list[tuple[str, str, int, int]]:
    tracker = QuotaTracker(storage_path=storage) if storage is not None else QuotaTracker()
    rows: list[tuple[str, str, int, int]] = []
    for key, usage in sorted(tracker.all_usage().items()):
        provider, window = key.split(":", 1)
        rows.append((provider, window, usage.used_requests, usage.used_tokens))
    return rows


def show_dashboard(history_path: Path | None = None, storage: Path | None = None) -> None:
    """Launch the optional Textual dashboard."""
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.widgets import DataTable, Footer, Header, Static
    except ImportError as exc:  # pragma: no cover - exercised through CLI tests
        raise RuntimeError(
            "dashboard dependencies are not installed. Install with: uv sync --extra tui --dev"
        ) from exc

    history_file = history_path or DEFAULT_HISTORY_PATH

    class SwarmDashboard(App):
        BINDINGS = [("q", "quit", "Quit"), ("r", "refresh", "Refresh")]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Horizontal(
                Vertical(Static("Quota Usage"), DataTable(id="quota_table")),
                Vertical(
                    Static("Consensus History"), DataTable(id="history_table"), Static(id="plot")
                ),
            )
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#quota_table", DataTable).add_columns(
                "Provider", "Window", "Requests", "Tokens"
            )
            self.query_one("#history_table", DataTable).add_columns(
                "Swarm", "Agreement", "Protocol"
            )
            self.set_interval(5.0, self.refresh_data)
            self.refresh_data()

        def action_refresh(self) -> None:
            self.refresh_data()

        def refresh_data(self) -> None:
            quota_table = self.query_one("#quota_table", DataTable)
            quota_table.clear()
            for provider, window, requests, tokens in _quota_rows(storage):
                quota_table.add_row(provider, window, str(requests), str(tokens))

            history = load_consensus_history(history_file)
            history_table = self.query_one("#history_table", DataTable)
            history_table.clear()
            for item in history:
                agreement = item.get("agreement", item.get("agreement_fraction", 0.0))
                history_table.add_row(
                    str(item.get("swarm_id", "")),
                    f"{float(agreement or 0.0):.2f}",
                    str(item.get("protocol", "")),
                )
            self.query_one("#plot", Static).update(build_agreement_plot(history))

    SwarmDashboard().run()


__all__ = [
    "DEFAULT_HISTORY_PATH",
    "build_agreement_plot",
    "load_consensus_history",
    "show_dashboard",
]
