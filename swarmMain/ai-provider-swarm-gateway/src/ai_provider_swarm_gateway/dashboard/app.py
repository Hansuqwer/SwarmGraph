"""
AGENT 27 — Provider Dashboard Agent
Rich CLI table + optional Streamlit dashboard.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..registry.loader import load_provider_registry

console = Console()


def _confidence_color(conf: str) -> str:
    return {"verified": "green", "partially_verified": "yellow",
            "unknown": "red", "likely_changed": "orange1"}.get(conf, "white")


def _bool_str(val: bool | None) -> str:
    if val is True:   return "✅ Yes"
    if val is False:  return "❌ No"
    return "❓ Unknown"


def show_provider_table(path: Path | None = None) -> None:
    """Print a Rich table of all providers to the terminal."""
    providers = load_provider_registry(path)
    table = Table(title="🤖 AI Provider Registry — Free Tier Overview", show_lines=True)

    table.add_column("Provider",         style="bold cyan",  width=20)
    table.add_column("API Free?",        width=10)
    table.add_column("Web Free Only?",   width=12)
    table.add_column("Daily Usage",      width=22)
    table.add_column("Monthly Usage",    width=22)
    table.add_column("Trial Credits",    width=18)
    table.add_column("Needs Card?",      width=10)
    table.add_column("Auth",             width=10)
    table.add_column("Confidence",       width=14)
    table.add_column("Last Verified",    width=12)
    table.add_column("Sign-Up",          width=40, no_wrap=False)

    for p in providers:
        conf_color = _confidence_color(p.quota.confidence)
        table.add_row(
            p.provider_name,
            _bool_str(p.quota.api_access_available),
            _bool_str(p.quota.web_only_free_access),
            p.quota.free_daily_usage or "—",
            p.quota.free_monthly_usage or "—",
            p.quota.trial_credits or "—",
            _bool_str(p.quota.requires_payment_method),
            ", ".join(p.auth_methods) or "—",
            Text(p.quota.confidence, style=conf_color),
            p.last_verified or "—",
            p.signup_url or p.website_url,
        )

    console.print(table)
    console.print()
    console.print("[bold]Legend:[/bold] ✅ = Yes  ❌ = No  ❓ = Unknown")
    console.print("[yellow]IMPORTANT:[/yellow] Verify all limits before production use. Data as of last_verified date.")


def show_provider_links(path: Path | None = None) -> None:
    """Print all provider links for easy access."""
    providers = load_provider_registry(path)
    table = Table(title="🔗 Provider Links", show_lines=True)
    table.add_column("Provider",    style="bold cyan", width=22)
    table.add_column("Website",     width=35)
    table.add_column("Sign Up",     width=40)
    table.add_column("Sign In",     width=40)
    table.add_column("API Docs",    width=40)
    table.add_column("Dashboard",   width=40)

    for p in providers:
        table.add_row(
            p.provider_name,
            p.website_url or "—",
            p.signup_url   or "—",
            p.signin_url   or "—",
            p.api_docs_url or "—",
            p.dashboard_url or "—",
        )
    console.print(table)


def launch_streamlit() -> None:
    """Launch the Streamlit dashboard (if streamlit is installed)."""
    import subprocess, sys
    app_path = Path(__file__).parent / "streamlit_app.py"
    if not app_path.exists():
        _write_streamlit_app(app_path)
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], check=True)


def _write_streamlit_app(path: Path) -> None:
    path.write_text(
        '''"""Streamlit provider dashboard."""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))
from src.ai_provider_swarm_gateway.registry.loader import load_provider_registry

st.set_page_config(page_title="AI Provider Gateway", layout="wide")
st.title("🤖 AI Provider Swarm Gateway — Provider Registry")
st.warning("All data should be verified before production use. Last verified dates are shown.")

providers = load_provider_registry()
rows = []
for p in providers:
    rows.append({
        "Provider": p.provider_name,
        "API Free?": "✅" if p.quota.api_access_available else ("❌" if p.quota.api_access_available is False else "❓"),
        "Web Free Only?": "✅" if p.quota.web_only_free_access else "—",
        "Daily Usage": p.quota.free_daily_usage or "—",
        "Monthly Usage": p.quota.free_monthly_usage or "—",
        "Trial Credits": p.quota.trial_credits or "—",
        "Needs Card?": "Yes" if p.quota.requires_payment_method else ("No" if p.quota.requires_payment_method is False else "?"),
        "Confidence": p.quota.confidence,
        "Last Verified": p.last_verified or "—",
        "Sign Up": p.signup_url or p.website_url or "—",
    })
import pandas as pd
st.dataframe(pd.DataFrame(rows), use_container_width=True)
st.caption("Source: providers.yaml · Verify all limits at provider documentation before use.")
''', encoding="utf-8")
