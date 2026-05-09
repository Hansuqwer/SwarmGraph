"""ai-provider-swarm-gateway — Typer CLI (v7).

v7 additions:
  - F-30-COSM1: Rich-escape the [no usage...] messages so they render
                instead of being swallowed as markup tags.
  - --tenant / AI_PROVIDER_GATEWAY_TENANT for multi-tenant quota isolation.
  - Interactive HITL: when --interactive (or stdin is a TTY) and a swarm
                hits awaiting_approval, prompt the operator. Single-use
                decision token preserved.

Preserves v6 surface:
  version, quota show/increment/reset/set-reset, providers list (filters,
  --since), inspect-state, route, swarm with --stream and --anti-drift.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import typer

try:
    from rich.console import Console
    from rich.markup import escape as _rich_escape
    from rich.panel import Panel
    from rich.table import Table

    _HAS_RICH = True
except ImportError:  # pragma: no cover
    _HAS_RICH = False

    def _rich_escape(s: str) -> str:
        return s


from .quota.tracker import QuotaTracker

app = typer.Typer(
    name="ai-provider-gateway",
    help="AI Provider Swarm Gateway — quota / providers / routing / swarm CLI.",
    no_args_is_help=True,
    add_completion=False,
)

quota_app = typer.Typer(name="quota", help="Local quota tracking.", no_args_is_help=True)
providers_app = typer.Typer(
    name="providers", help="Provider registry inspection.", no_args_is_help=True
)
tenants_app = typer.Typer(
    name="tenants", help="Multi-tenant quota management.", no_args_is_help=True
)
pool_app = typer.Typer(
    name="pool", help="Encrypted account vault management.", no_args_is_help=True
)
auth_app = typer.Typer(name="auth", help="Opt-in auth helpers.", no_args_is_help=True)
audit_app = typer.Typer(
    name="audit",
    help="Verify HMAC-SHA256-signed audit logs.",
    no_args_is_help=True,
)
app.add_typer(quota_app)
app.add_typer(providers_app)
app.add_typer(tenants_app)
app.add_typer(auth_app)
app.add_typer(audit_app)
tenants_app.add_typer(pool_app)

_console = Console() if _HAS_RICH else None


# ── Helpers ────────────────────────────────────────────────────────────────


def _resolve_storage_path(custom: Path | None, tenant: str | None = None) -> Path | None:
    """Return the storage path; None means 'let QuotaTracker decide from tenant_id or env'."""
    if custom is not None:
        return custom
    env_override = os.environ.get("AI_PROVIDER_GATEWAY_USAGE_PATH")
    if env_override:
        return Path(env_override)
    return None  # tracker will use tenant_id or default


def _build_tracker(
    storage: Path | None,
    tenant: str | None,
) -> QuotaTracker:
    """Build a QuotaTracker honouring --storage / --tenant / env precedence."""
    sp = _resolve_storage_path(storage, tenant)
    if sp is not None:
        return QuotaTracker(storage_path=sp)
    if tenant:
        return QuotaTracker(tenant_id=tenant)
    return QuotaTracker()  # will read AI_PROVIDER_GATEWAY_TENANT env


def _print(text: str) -> None:
    """F-30-COSM1: route through Rich with markup interpretation enabled
    OR plain print if Rich is absent. Callers that pass user-content
    strings should use _print_plain instead."""
    (_console.print if _console else print)(text)


def _print_plain(text: str) -> None:
    """F-30-COSM1: emit text WITHOUT Rich markup interpretation.

    Avoids the bug where '[no usage recorded yet]' was being parsed as a
    style tag and rendered as nothing.
    """
    if _console:
        _console.print(_rich_escape(text))
    else:
        print(text)


def _err(text: str) -> None:
    if _console:
        _console.print(f"[red]{_rich_escape(text)}[/red]")
    else:
        print(text, file=sys.stderr)


_DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$")


def _parse_duration_to_seconds(s: str) -> int:
    m = _DURATION_RE.match(s.strip().lower())
    if not m:
        raise ValueError(f"invalid duration {s!r}; use Ns | Nm | Nh | Nd (e.g. '30m', '1h', '7d')")
    n = int(m.group(1))
    unit = m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError("expected s3://bucket/prefix")
    return parsed.netloc, parsed.path.strip("/") or "audit"


def _load_s3_audit_backend_class():
    try:
        from swarm_shared.audit_backends import S3AuditBackend
    except ImportError as e:
        raise RuntimeError(
            "S3 audit support is unavailable; install S3 support with the s3 extra"
        ) from e
    return S3AuditBackend


# ── version ────────────────────────────────────────────────────────────────


@app.command()
def version() -> None:
    """Print package versions."""
    try:
        from importlib.metadata import version as _v
    except ImportError:  # pragma: no cover
        _print("importlib.metadata not available")
        raise typer.Exit(1)

    rows = []
    for name in (
        "ai-provider-swarm-gateway",
        "swarm-shared",
        "hive-swarm",
        "pydantic",
        "langgraph",
        "typer",
        "rich",
        "pyyaml",
    ):
        try:
            rows.append((name, _v(name)))
        except Exception:
            rows.append((name, "<not installed>"))

    if _HAS_RICH and _console:
        t = Table(title="Versions")
        t.add_column("Package")
        t.add_column("Version")
        for n, v in rows:
            t.add_row(n, v)
        _console.print(t)
    else:
        for n, v in rows:
            print(f"{n:35s} {v}")


# ── quota subcommands ─────────────────────────────────────────────────────


@quota_app.command("show")
def quota_show(
    provider: str | None = typer.Option(None, "--provider", "-p"),
    window: str = typer.Option("daily", "--window", "-w"),
    storage: Path | None = typer.Option(None, "--storage"),
    tenant: str | None = typer.Option(
        None, "--tenant", help="v7: tenant id for multi-tenant isolation"
    ),
    since: str | None = typer.Option(None, "--since"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show current quota usage."""
    tracker = _build_tracker(storage, tenant)

    cutoff: datetime | None = None
    if since:
        try:
            seconds = _parse_duration_to_seconds(since)
            cutoff = datetime.now(tz=UTC) - timedelta(seconds=seconds)
        except ValueError as e:
            _err(f"❌ {e}")
            raise typer.Exit(2)

    if provider:
        rows = [(provider, window, tracker.get_usage(provider, window))]
    else:
        all_usage = tracker.all_usage()
        if not all_usage:
            # F-30-COSM1: use _print_plain to avoid Rich markup swallowing
            _print_plain("[no usage recorded yet]")
            raise typer.Exit(0)
        rows = []
        for key, usage in sorted(all_usage.items()):
            pid, win = key.split(":", 1)
            rows.append((pid, win, usage))

    if cutoff is not None:
        filtered = []
        for pid, win, u in rows:
            if u.used_requests == 0 and u.used_tokens == 0:
                continue
            ra = u.reset_at
            if ra is None:
                filtered.append((pid, win, u))
                continue
            if ra.tzinfo is None:
                ra = ra.replace(tzinfo=UTC)
            if ra >= cutoff:
                filtered.append((pid, win, u))
        rows = filtered
        if not rows:
            # F-30-COSM1
            _print_plain(f"[no usage in last {since}]")
            raise typer.Exit(0)

    if json_output:
        payload = [
            {
                "provider": pid,
                "window": win,
                "tenant": tracker.tenant_id,
                "used_requests": u.used_requests,
                "used_tokens": u.used_tokens,
                "reset_at": u.reset_at.isoformat() if u.reset_at else None,
            }
            for pid, win, u in rows
        ]
        print(json.dumps(payload, indent=2))
        return

    if _HAS_RICH and _console:
        title_parts = [f"Quota usage ({tracker.storage_path})"]
        if tracker.tenant_id:
            title_parts.append(f"tenant={tracker.tenant_id}")
        if cutoff:
            title_parts.append(f"since {since}")
        t = Table(title=" — ".join(title_parts))
        t.add_column("Provider")
        t.add_column("Window")
        t.add_column("Requests", justify="right")
        t.add_column("Tokens", justify="right")
        t.add_column("Reset at")
        for pid, win, u in rows:
            t.add_row(
                pid,
                win,
                str(u.used_requests),
                str(u.used_tokens),
                u.reset_at.isoformat() if u.reset_at else "—",
            )
        _console.print(t)
    else:
        print(f"# storage: {tracker.storage_path}")
        if tracker.tenant_id:
            print(f"# tenant:  {tracker.tenant_id}")
        for pid, win, u in rows:
            reset = u.reset_at.isoformat() if u.reset_at else "—"
            print(
                f"{pid:20s} {win:8s} req={u.used_requests:8d} tok={u.used_tokens:10d} reset={reset}"
            )


@quota_app.command("increment")
def quota_increment(
    provider: str = typer.Option(..., "--provider", "-p"),
    requests: int = typer.Option(0, "--requests", "-r", min=0),
    tokens: int = typer.Option(0, "--tokens", "-t", min=0),
    window: str = typer.Option("daily", "--window", "-w"),
    storage: Path | None = typer.Option(None, "--storage"),
    tenant: str | None = typer.Option(None, "--tenant"),
) -> None:
    if requests == 0 and tokens == 0:
        _err("Nothing to increment: pass --requests and/or --tokens.")
        raise typer.Exit(2)
    tracker = _build_tracker(storage, tenant)
    new_usage = tracker.increment(provider, requests=requests, tokens=tokens, window=window)
    tenant_label = f" tenant={tracker.tenant_id}" if tracker.tenant_id else ""
    _print(
        f"✅ {provider} ({window}){tenant_label}: requests={new_usage.used_requests}, tokens={new_usage.used_tokens}"
    )


@quota_app.command("reset")
def quota_reset(
    provider: str = typer.Option(..., "--provider", "-p"),
    window: str = typer.Option("daily", "--window", "-w"),
    storage: Path | None = typer.Option(None, "--storage"),
    tenant: str | None = typer.Option(None, "--tenant"),
    confirm: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    if not confirm:
        typer.confirm(f"Reset {provider}:{window} usage to zero?", abort=True)
    tracker = _build_tracker(storage, tenant)
    if hasattr(tracker, "reset_usage"):
        tracker.reset_usage(provider, window)
    else:
        tracker.set_reset_time(provider, datetime.now(tz=UTC), window)
    after = tracker.get_usage(provider, window)
    _print(f"✅ {provider} ({window}) reset → req={after.used_requests}, tok={after.used_tokens}")


@quota_app.command("set-reset")
def quota_set_reset(
    provider: str = typer.Option(..., "--provider", "-p"),
    in_hours: float = typer.Option(24.0, "--in-hours"),
    window: str = typer.Option("daily", "--window", "-w"),
    storage: Path | None = typer.Option(None, "--storage"),
    tenant: str | None = typer.Option(None, "--tenant"),
) -> None:
    when = datetime.now(tz=UTC) + timedelta(hours=in_hours)
    tracker = _build_tracker(storage, tenant)
    tracker.set_reset_time(provider, when, window)
    _print(f"✅ {provider} ({window}) reset scheduled for {when.isoformat()}")


# ── tenants subcommands (v7 NEW) ─────────────────────────────────────────


@tenants_app.command("list")
def tenants_list(
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List tenants with a usage.json on disk."""
    ids = QuotaTracker.list_tenants()
    if json_output:
        print(json.dumps(ids))
        return
    if not ids:
        _print_plain("[no tenants found]")
        return
    for tid in ids:
        path = QuotaTracker.tenant_storage_path(tid)
        print(f"{tid:30s} {path}")


@tenants_app.command("storage-path")
def tenants_storage_path(
    tenant_id: str = typer.Argument(...),
) -> None:
    """Print the canonical storage path for a tenant id."""
    print(QuotaTracker.tenant_storage_path(tenant_id))


# ── encrypted account pool subcommands ──────────────────────────────────


@pool_app.command("init")
def pool_init(
    key_path: Path = typer.Option(Path.home() / ".ai_provider_gateway" / "vault.key", "--key-path"),
) -> None:
    """Create a new local vault key file with 0600 permissions."""
    try:
        from .quota.pool import create_vault_key

        create_vault_key(key_path)
    except Exception as exc:
        _err(f"could not initialize vault key: {exc}")
        raise typer.Exit(1) from exc
    _print_plain(f"created vault key: {key_path}")


@pool_app.command("add")
def pool_add(
    provider: str = typer.Argument(...),
    account_id: str = typer.Argument(...),
    secret: str = typer.Option(..., "--secret", prompt=True, hide_input=True),
    vault_path: Path | None = typer.Option(None, "--vault-path"),
    key_path: Path | None = typer.Option(None, "--key-path"),
) -> None:
    """Add or update one encrypted account secret. Secret is never printed."""
    try:
        from .quota.pool import DEFAULT_KEY_PATH, DEFAULT_VAULT_PATH, SecretStore

        store = SecretStore(
            vault_path or DEFAULT_VAULT_PATH,
            key_path=key_path or DEFAULT_KEY_PATH,
        )
        store.add_key(provider, account_id, secret)
    except Exception as exc:
        _err(f"could not store account secret: {exc}")
        raise typer.Exit(1) from exc
    _print_plain(f"stored account provider={provider} account={account_id}")


@pool_app.command("list")
def pool_list(
    vault_path: Path | None = typer.Option(None, "--vault-path"),
    key_path: Path | None = typer.Option(None, "--key-path"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List provider/account IDs in the encrypted vault, never secrets."""
    try:
        from .quota.pool import DEFAULT_KEY_PATH, DEFAULT_VAULT_PATH, SecretStore

        summary = SecretStore(
            vault_path or DEFAULT_VAULT_PATH,
            key_path=key_path or DEFAULT_KEY_PATH,
        ).to_summary()
    except Exception as exc:
        _err(f"could not read encrypted vault: {exc}")
        raise typer.Exit(1) from exc
    if json_output:
        print(json.dumps(summary, sort_keys=True))
        return
    if not summary:
        _print_plain("[no accounts found]")
        return
    for provider, account_ids in summary.items():
        for account_id in account_ids:
            _print_plain(f"{provider:20s} {account_id}")


@pool_app.command("sync")
def pool_sync(
    bucket: str = typer.Option(..., "--bucket", "-b"),
    key: str = typer.Option("secrets.json.enc", "--key", "-k"),
    vault_path: Path | None = typer.Option(None, "--vault-path"),
    push: bool = typer.Option(False, "--push"),
    pull: bool = typer.Option(False, "--pull"),
) -> None:
    """Push/pull the encrypted vault blob to S3. Secrets are not logged."""
    if push == pull:
        _err("choose exactly one of --push or --pull")
        raise typer.Exit(2)
    try:
        import boto3  # type: ignore[import-not-found]
        from boto3.s3.transfer import TransferConfig  # type: ignore[import-not-found]

        from .quota.pool import DEFAULT_VAULT_PATH

        path = vault_path or DEFAULT_VAULT_PATH
        config = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,
            max_concurrency=10,
            use_threads=True,
        )
        s3 = boto3.client("s3")
        if push:
            if not path.exists():
                _err(f"vault file not found: {path}")
                raise typer.Exit(1)
            s3.upload_file(str(path), bucket, key, Config=config)
            _print_plain(f"pushed encrypted vault to s3://{bucket}/{key}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(path), Config=config)
            os.chmod(path, 0o600)
            _print_plain(f"pulled encrypted vault from s3://{bucket}/{key}")
    except typer.Exit:
        raise
    except Exception as exc:
        _err(f"vault sync failed: {exc}")
        raise typer.Exit(1) from exc


# ── auth subcommands ────────────────────────────────────────────────────


@auth_app.command("import-browser")
def auth_import_browser(
    provider: str = typer.Argument(..., help="Provider: chatgpt, qwen, or kimi."),
    browser: str = typer.Option("chrome", "--browser", help="Browser to inspect."),
    account_id: str = typer.Option("browser_auto", "--account-id"),
    vault_path: Path | None = typer.Option(None, "--vault-path"),
    key_path: Path | None = typer.Option(None, "--key-path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Find token but do not store it."),
) -> None:
    """Import a local browser session token into the encrypted vault.

    Explicit opt-in only. The token value is never printed.
    """
    try:
        from .auth_browser import BrowserAuthError, extract_browser_session_token
    except ImportError as exc:
        _err(f"browser auth unavailable: {exc}")
        raise typer.Exit(1) from exc

    try:
        token = extract_browser_session_token(
            provider,
            browser=browser,
            account_id=account_id,
        )
    except BrowserAuthError as exc:
        _err(str(exc))
        raise typer.Exit(2) from exc
    if token is None:
        _err(f"no {provider} session token found in {browser}")
        raise typer.Exit(1)

    if dry_run:
        _print_plain(
            f"found {token.provider} token in {token.source_browser} "
            f"cookie={token.cookie_name}; not stored"
        )
        return

    try:
        from .quota.pool import DEFAULT_KEY_PATH, DEFAULT_VAULT_PATH, SecretStore

        store = SecretStore(
            vault_path or DEFAULT_VAULT_PATH,
            key_path=key_path or DEFAULT_KEY_PATH,
        )
        store.add_key(token.provider, token.account_id, token.token)
    except Exception as exc:
        _err(f"could not store browser token in encrypted vault: {exc}")
        raise typer.Exit(3) from exc
    _print_plain(
        f"stored {token.provider} token account={token.account_id} "
        f"source={token.source_browser} cookie={token.cookie_name}"
    )


# ── providers subcommands (unchanged from v6) ────────────────────────────


def _try_load_registry() -> list[dict] | None:
    here = Path(__file__).resolve().parent
    candidates = [here / "registry" / "providers.yaml", here / "registry" / "providers.json"]
    raw: Any = None
    for p in candidates:
        if not p.exists():
            continue
        if p.suffix == ".yaml":
            try:
                import yaml  # type: ignore
            except ImportError:
                _err("PyYAML not installed.")
                return None
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        else:
            raw = json.loads(p.read_text(encoding="utf-8"))
        break
    if raw is None:
        return None
    if isinstance(raw, dict) and "providers" in raw:
        items = raw["providers"]
    elif isinstance(raw, list):
        items = raw
    else:
        return None
    normalised = []
    for p in items:
        if not isinstance(p, dict):
            continue
        item = dict(p)
        if "name" not in item and "provider_name" in item:
            item["name"] = item["provider_name"]
        normalised.append(item)
    return normalised


@providers_app.command("list")
def providers_list(
    json_output: bool = typer.Option(False, "--json"),
    capability: str | None = typer.Option(None, "--capability", "-c"),
    free_only: bool = typer.Option(False, "--free-only"),
) -> None:
    registry = _try_load_registry()
    if registry is None:
        _err("ℹ️  No registry/providers.{yaml,json} found.")
        raise typer.Exit(2)
    if capability:
        registry = [p for p in registry if capability in (p.get("capabilities") or [])]
    if free_only:

        def _is_free(p: dict) -> bool:
            if p.get("is_local"):
                return True
            quota = p.get("quota") or {}
            return bool(quota.get("free_daily_usage")) or bool(p.get("free"))

        registry = [p for p in registry if _is_free(p)]

    if json_output:
        print(json.dumps(registry, indent=2, default=str))
        return

    if _HAS_RICH and _console:
        t = Table(title=f"Providers ({len(registry)})")
        t.add_column("ID")
        t.add_column("Name")
        t.add_column("Capabilities")
        t.add_column("Local?")
        t.add_column("Free tier")
        for p in registry:
            quota = p.get("quota") or {}
            t.add_row(
                str(p.get("provider_id", "?")),
                str(p.get("name", "?")),
                ", ".join(p.get("capabilities") or []),
                "yes" if p.get("is_local") else "no",
                str(quota.get("free_daily_usage") or "—"),
            )
        _console.print(t)
    else:
        for p in registry:
            print(f"- {p.get('provider_id'):25s} {p.get('name')} — caps={p.get('capabilities')}")


# ── route — preserved (v6 + canonical missing-gateway message) ──────────

_MISSING_GATEWAY_MSG = (
    "❌ Upstream gateway modules missing: {err}\n"
    "   Vendor them into src/ai_provider_swarm_gateway/:\n"
    "     models/state.py, graph/builder.py, graph/nodes.py,\n"
    "     consensus/strategies.py, policy/guardrails.py,\n"
    "     providers/*_adapter.py, registry/loader.py + providers.yaml\n"
    "   See PATCH_NOTE_2026-05-07.md for re-fetch instructions."
)


def _import_gateway_pieces():
    from .graph.builder import build_gateway_graph  # type: ignore
    from .models.state import GatewayState  # type: ignore

    try:
        from .models.state import RoutingDecision  # type: ignore
    except Exception:
        RoutingDecision = None
    return GatewayState, build_gateway_graph, RoutingDecision


def _build_initial_state(GatewayState, *, prompt, capability, preferred, allow_unknown_quota):
    candidate_kwargs = {
        "user_prompt": prompt,
        "requested_capability": capability,
        "preferred_provider_id": preferred,
        "allow_unknown_quota": allow_unknown_quota,
        "is_safe_to_proceed": True,
        "audit_log": [],
        "candidate_providers": [],
    }
    declared = set(getattr(GatewayState, "model_fields", {}).keys())
    init_kwargs = {k: v for k, v in candidate_kwargs.items() if k in declared}
    init_kwargs.setdefault("user_prompt", prompt)
    return GatewayState(**init_kwargs)


def _extract_field(state, *names, default=None):
    for n in names:
        if hasattr(state, n):
            v = getattr(state, n)
            if v is not None:
                return v
        if isinstance(state, dict) and n in state:
            return state[n]
    return default


@app.command("route")
def route(
    prompt: str = typer.Option(..., "--prompt"),
    capability: str | None = typer.Option(None, "--capability", "-c"),
    preferred: str | None = typer.Option(None, "--preferred"),
    thread_id: str | None = typer.Option(None, "--thread-id"),
    allow_unknown_quota: bool = typer.Option(False, "--allow-unknown-quota"),
    json_output: bool = typer.Option(False, "--json"),
    show_audit: bool = typer.Option(False, "--show-audit"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Route a prompt through the 9-node gateway graph."""
    try:
        GatewayState, build_gateway_graph, _RoutingDecision = _import_gateway_pieces()
    except ImportError as e:
        _err(_MISSING_GATEWAY_MSG.format(err=e))
        raise typer.Exit(2)

    try:
        state = _build_initial_state(
            GatewayState,
            prompt=prompt,
            capability=capability,
            preferred=preferred,
            allow_unknown_quota=allow_unknown_quota,
        )
    except Exception as e:
        _err(f"❌ Could not construct GatewayState: {e}")
        raise typer.Exit(2)

    try:
        graph = build_gateway_graph()
    except TypeError:
        try:
            graph = build_gateway_graph(state)
        except Exception as e:
            _err(f"❌ build_gateway_graph() failed: {e}")
            raise typer.Exit(2)
    except Exception as e:
        _err(f"❌ build_gateway_graph() failed: {e}")
        raise typer.Exit(2)

    tid = thread_id or f"cli-{uuid.uuid4().hex[:12]}"

    try:
        init_payload = (
            state.to_json_dict()
            if hasattr(state, "to_json_dict")
            else state.model_dump(mode="json")
        )
        try:
            result = graph.invoke(init_payload, config={"configurable": {"thread_id": tid}})
        except TypeError:
            result = graph.invoke(init_payload)
    except Exception as e:
        _err(f"❌ Graph invocation failed: {e}")
        raise typer.Exit(3)

    try:
        final_state = (
            GatewayState.from_json_dict(result)
            if hasattr(GatewayState, "from_json_dict")
            else GatewayState.model_validate(result)
        )
    except Exception:
        final_state = result

    selected = _extract_field(
        final_state,
        "selected_provider_id",
        "chosen_provider_id",
        "winning_provider_id",
        "routing_decision",
        default=None,
    )
    if hasattr(selected, "provider_id"):
        selected = selected.provider_id
    elif hasattr(selected, "selected_provider_id"):
        selected = selected.selected_provider_id

    candidates = _extract_field(final_state, "candidate_providers", default=[])
    response_text = _extract_field(
        final_state,
        "response_text",
        "final_response",
        "response",
        "validated_response",
        "provider_response",
        default="",
    )
    if hasattr(response_text, "content"):
        response_text = response_text.content
    elif hasattr(response_text, "text"):
        response_text = response_text.text

    is_safe = _extract_field(final_state, "is_safe_to_proceed", default=True)
    errors = _extract_field(final_state, "errors", default=[])
    policy_violations = _extract_field(final_state, "policy_violations", default=[])
    audit_log = _extract_field(final_state, "audit_log", default=[])

    if json_output:
        payload = {
            "thread_id": tid,
            "prompt": prompt,
            "capability": capability,
            "is_safe_to_proceed": bool(is_safe),
            "candidate_providers": list(candidates) if candidates else [],
            "selected_provider": selected
            if isinstance(selected, str)
            else (str(selected) if selected else None),
            "response_text": response_text
            if isinstance(response_text, str)
            else str(response_text or ""),
            "errors": list(errors) if errors else [],
            "policy_violations": list(policy_violations) if policy_violations else [],
            "audit_log_lines": len(audit_log) if audit_log else 0,
        }
        print(json.dumps(payload))
        if show_audit:
            print(json.dumps({"audit_log": list(audit_log) if audit_log else []}))
        if not is_safe or (selected is None and not dry_run):
            raise typer.Exit(4)
        return

    if _HAS_RICH and _console:
        _console.rule(f"[bold]route[/bold] thread={tid}")
        _console.print(Panel(_rich_escape(prompt), title="Prompt"))
        if not is_safe:
            _console.print("[red]is_safe_to_proceed = False[/red]")
        if candidates:
            _console.print(f"[dim]Candidates ({len(candidates)}):[/dim] " + ", ".join(candidates))
        if selected:
            _console.print(f"[green]Selected:[/green] {selected}")
        else:
            _console.print("[yellow]No provider selected.[/yellow]")
        if response_text:
            _console.print(Panel(_rich_escape(str(response_text)), title="Response"))
        if errors:
            _console.print(
                Panel("\n".join(_rich_escape(str(e)) for e in errors), title="Errors", style="red")
            )
        if show_audit and audit_log:
            _console.print(
                Panel("\n".join(_rich_escape(str(line)) for line in audit_log), title="Audit log")
            )
    else:
        print(f"thread:    {tid}")
        print(f"prompt:    {prompt}")
        print(f"selected:  {selected}")
        if response_text:
            print(f"response:  {response_text}")

    if not is_safe:
        raise typer.Exit(4)
    if selected is None and not dry_run:
        raise typer.Exit(4)


# ── inspect-state — preserved ────────────────────────────────────────────


@app.command("inspect-state")
def inspect_state(json_output: bool = typer.Option(False, "--json")) -> None:
    try:
        from .models.state import GatewayState  # type: ignore
    except ImportError as e:
        _err(f"❌ Cannot import GatewayState: {e}")
        raise typer.Exit(2)

    fields = getattr(GatewayState, "model_fields", {}) or {}
    rows = []
    for name, info in fields.items():
        try:
            ann = getattr(info, "annotation", "?")
            req = info.is_required() if hasattr(info, "is_required") else True
            default = getattr(info, "default", None)
            rows.append((name, str(ann), "required" if req else "optional", repr(default)))
        except Exception:
            rows.append((name, "?", "?", "?"))

    if json_output:
        print(
            json.dumps(
                [
                    {
                        "name": r[0],
                        "annotation": r[1],
                        "required": r[2] == "required",
                        "default": r[3],
                    }
                    for r in rows
                ],
                indent=2,
            )
        )
        return

    if _HAS_RICH and _console:
        t = Table(title=f"GatewayState fields ({len(rows)})")
        t.add_column("Field")
        t.add_column("Type")
        t.add_column("Req?")
        t.add_column("Default")
        for r in rows:
            t.add_row(*r)
        _console.print(t)
    else:
        for r in rows:
            print(f"{r[0]:30s} {r[2]:8s} {r[1]}  default={r[3]}")


# ── v8: audit verify subcommand ─────────────────────────────────────────


@audit_app.command("verify")
def audit_verify(
    log_path: str = typer.Argument(
        ...,
        help="Path to JSONL audit log or s3://bucket/prefix.",
    ),
    secret_env: str = typer.Option(
        "HIVE_SWARM_AUDIT_SECRET",
        "--secret-env",
        help="Env var holding the HMAC secret used to sign the log.",
    ),
    json_output: bool = typer.Option(False, "--json"),
    expected_head_hash: str | None = typer.Option(
        None,
        "--expected-head-hash",
        help="Expected final audit-chain head hash.",
    ),
    expected_count: int | None = typer.Option(
        None,
        "--expected-count",
        help="Expected number of audit records.",
    ),
    swarm_id: str | None = typer.Option(
        None,
        "--swarm-id",
        help="Swarm ID required when verifying s3:// audit logs.",
    ),
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
        _err("required audit secret environment variable is unset; cannot verify signatures")
        raise typer.Exit(1)

    try:
        if log_path.startswith("s3://"):
            if not swarm_id:
                _err("--swarm-id is required when verifying s3:// audit logs")
                raise typer.Exit(2)
            bucket, prefix = _parse_s3_uri(log_path)
            backend_cls = _load_s3_audit_backend_class()
            records = backend_cls(bucket=bucket, prefix=prefix).load(swarm_id)
        else:
            path = Path(log_path)
            if not path.exists() or not path.is_file():
                _err(f"audit log not found: {log_path}")
                raise typer.Exit(2)
            records = load_jsonl_chain(path)
    except typer.Exit:
        raise
    except Exception as e:
        _err(f"audit log malformed: {e}")
        raise typer.Exit(2)

    if not records:
        if expected_count not in (None, 0):
            error = f"record count mismatch: expected={expected_count}, got=0"
            if json_output:
                print(json.dumps({"verified": 0, "ok": False, "error": error}))
            else:
                _err(f"❌ chain broken: {error}")
            raise typer.Exit(3)
        if expected_head_hash is not None and expected_head_hash != "GENESIS":
            error = "head hash mismatch: expected non-GENESIS, got GENESIS"
            if json_output:
                print(json.dumps({"verified": 0, "ok": False, "error": error}))
            else:
                _err(f"❌ chain broken: {error}")
            raise typer.Exit(3)
        if json_output:
            payload: dict[str, Any] = {"verified": 0, "ok": True, "reason": "empty log"}
            if expected_head_hash is not None:
                payload["expected_head_hash"] = expected_head_hash
            if expected_count is not None:
                payload["expected_count"] = expected_count
            print(json.dumps(payload))
        else:
            _print_plain("[empty audit log]")
        return

    try:
        count = verify_chain(
            records,
            secret=secret.encode("utf-8"),
            expected_head_hash=expected_head_hash,
            expected_count=expected_count,
        )
    except AuditChainBroken as e:
        if json_output:
            print(
                json.dumps(
                    {
                        "verified": 0,
                        "ok": False,
                        "total_records": len(records),
                        "error": str(e),
                    }
                )
            )
        else:
            _err(f"❌ chain broken: {e}")
        raise typer.Exit(3)

    # Summary by kind
    by_kind: dict[str, int] = {}
    for r in records:
        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1

    if json_output:
        payload = {
            "verified": count,
            "ok": True,
            "total_records": len(records),
            "swarm_ids": sorted({r.swarm_id for r in records}),
            "by_kind": by_kind,
        }
        if expected_head_hash is not None:
            payload["expected_head_hash"] = expected_head_hash
        if expected_count is not None:
            payload["expected_count"] = expected_count
        print(json.dumps(payload, indent=2))
    else:
        if _HAS_RICH and _console:
            t = Table(title=f"Audit log verified: {log_path}")
            t.add_column("Kind")
            t.add_column("Count", justify="right")
            for kind, n in sorted(by_kind.items()):
                t.add_row(kind, str(n))
            _console.print(t)
            _console.print(f"[green]✅ {count} records verified, chain intact[/green]")
        else:
            print(f"✅ verified {count} records")
            for kind, n in sorted(by_kind.items()):
                print(f"  {kind:25s} {n}")


@audit_app.command("restore")
def audit_restore(
    bucket: str = typer.Argument(..., help="S3 bucket containing audit logs."),
    swarm_id: str = typer.Argument(..., help="Swarm ID to restore."),
    prefix: str = typer.Option("audit", "--prefix", help="S3 prefix for audit partitions."),
    tier: str = typer.Option("Bulk", "--tier", help="Restore tier: Bulk, Standard, or Expedited."),
    days: int = typer.Option(30, "--days", min=1, help="Number of days to keep restored copy."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Initiate restore requests for archived S3 audit log partitions."""
    try:
        backend_cls = _load_s3_audit_backend_class()
        restored = backend_cls(bucket=bucket, prefix=prefix).restore_archive(
            swarm_id,
            days=days,
            tier=tier,
        )
    except Exception as e:
        if json_output:
            print(json.dumps({"ok": False, "error": str(e)}))
        else:
            _err(f"audit restore failed: {e}")
        raise typer.Exit(2)

    payload = {
        "ok": True,
        "bucket": bucket,
        "prefix": prefix,
        "swarm_id": swarm_id,
        "restored": restored,
        "tier": tier,
        "days": days,
    }
    if json_output:
        print(json.dumps(payload, indent=2))
    else:
        _print_plain(f"restore requested for {restored} audit object(s)")


@app.command("dashboard")
def dashboard(
    history_path: Path | None = typer.Option(
        None,
        "--history-path",
        help="Path to consensus_history.jsonl.",
    ),
    storage: Path | None = typer.Option(
        None,
        "--storage",
        help="Quota usage JSON path.",
    ),
) -> None:
    """Launch the optional Textual monitoring dashboard."""
    try:
        from .dashboard import show_dashboard

        show_dashboard(history_path=history_path, storage=storage)
    except RuntimeError as e:
        _err(str(e))
        raise typer.Exit(1)
    except ImportError as e:
        _err("dashboard dependencies are not installed. Install with: uv sync --extra tui --dev")
        raise typer.Exit(1) from e


# ── v8: streaming HITL prompt helper ────────────────────────────────────


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
    """
    if _HAS_RICH and _console:
        _console.rule(f"[bold yellow]Streaming HITL[/bold yellow] swarm={swarm_id}")
        _console.print(f"[dim]reason[/dim] {reason}  [dim]token[/dim] {decision_token[:8]}…")
        if matched_pattern:
            _console.print(f"[dim]matched_pattern[/dim] {matched_pattern!r}")
        _console.print(
            Panel(
                _rich_escape(partial_text[:2000]),
                title=f"Partial output ({len(partial_text)} chars)",
            )
        )
    else:
        print(f"# Streaming HITL — swarm={swarm_id}")
        print(f"# reason={reason}  token={decision_token[:8]}…")
        if matched_pattern:
            print(f"# matched_pattern={matched_pattern!r}")
        print(f"# partial output ({len(partial_text)} chars):")
        print(partial_text[:2000])

    reviewer_id = (
        os.environ.get("AI_PROVIDER_GATEWAY_REVIEWER_ID") or os.environ.get("USER") or "cli"
    )

    try:
        choice = (
            typer.prompt(
                "Action? (a=abort / c=continue / p=accept_partial)",
                default="a",
            )
            .strip()
            .lower()
        )
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


# ── v7: interactive HITL prompt helper ──────────────────────────────────


def _interactive_hitl_prompt(swarm_id: str, payload: dict) -> dict | None:
    """Print the consensus snapshot and prompt the operator.

    Returns a decision dict shaped for `Command(resume=...)`:
        {"decision": "approve" | "deny",
         "reviewer_id": "<resolved>",
         "decision_token": "<echoed>"}

    Returns None if the operator's response can't be parsed (caller treats
    as deny). Single-use guarantee: the issued decision_token is echoed
    verbatim and verified upstream.
    """
    proposed = str(payload.get("proposed_action_preview") or payload.get("proposed_action") or "")
    risk = payload.get("risk_score", "?")
    agree = payload.get("agreement_fraction", "?")
    proto = payload.get("protocol", "?")
    token = str(payload.get("decision_token_required") or payload.get("decision_token") or "")
    if _HAS_RICH and _console:
        _console.rule(f"[bold yellow]HITL approval required[/bold yellow] swarm={swarm_id}")
        _console.print(
            f"[dim]protocol[/dim] {proto}  [dim]agreement[/dim] {agree}  [dim]risk[/dim] {risk}"
        )
        _console.print(Panel(_rich_escape(proposed[:1500]), title="Proposed action"))
        _console.print("[dim]token[/dim] " + token[:8] + "…")
    else:
        print(f"# HITL approval required — swarm={swarm_id}")
        print(f"# protocol={proto} agreement={agree} risk={risk}")
        print(f"# token={token[:8]}…")
        print("# proposed action:")
        print(proposed[:1500])

    reviewer_id = (
        os.environ.get("AI_PROVIDER_GATEWAY_REVIEWER_ID") or os.environ.get("USER") or "cli"
    )

    try:
        decision = (
            typer.prompt(
                "Approve this action? (y/n)",
                default="n",
            )
            .strip()
            .lower()
        )
    except (EOFError, KeyboardInterrupt):
        return None

    if decision in ("y", "yes", "approve", "approved"):
        action = "approve"
    elif decision in ("n", "no", "deny", "denied"):
        action = "deny"
    else:
        return None

    return {
        "decision": action,
        "reviewer_id": reviewer_id,
        "decision_token": token,
    }


# ── swarm — v7 (adds --interactive HITL + --tenant) ─────────────────────


@app.command("swarm")
def swarm(
    prompt: str = typer.Option(..., "--prompt", "-p"),
    topology: str = typer.Option("hierarchical", "--topology"),
    consensus: str = typer.Option("raft", "--consensus"),
    max_agents: int = typer.Option(5, "--max-agents", min=1, max=100),
    backend: str = typer.Option("stub", "--backend"),
    provider: str = typer.Option("9router", "--provider"),
    model: str | None = typer.Option(None, "--model"),
    max_tokens: int = typer.Option(512, "--max-tokens", min=1),
    temperature: float = typer.Option(0.0, "--temperature", min=0.0, max=2.0),
    sona: bool = typer.Option(True, "--sona/--no-sona"),
    auto_approve: bool = typer.Option(True, "--auto-approve/--no-auto-approve"),
    thread_id: str | None = typer.Option(None, "--thread-id"),
    json_output: bool = typer.Option(False, "--json"),
    show_workers: bool = typer.Option(False, "--show-workers"),
    anti_drift_mode: str = typer.Option("keyword", "--anti-drift"),
    stream: bool = typer.Option(False, "--stream"),
    no_cost: bool = typer.Option(False, "--no-cost"),
    # v7
    interactive: bool = typer.Option(
        False,
        "--interactive/--no-interactive",
        help="v7: prompt operator on HITL approval; auto-detects TTY when --interactive omitted.",
    ),
    tenant: str | None = typer.Option(
        None,
        "--tenant",
        help="v7: tenant id for quota isolation (env: AI_PROVIDER_GATEWAY_TENANT).",
    ),
) -> None:
    """Route a prompt through hive-swarm with the gateway underneath."""
    try:
        from langgraph.types import Command
        from swarm import SwarmConfig, SwarmState, build_swarm_graph
    except ImportError as e:
        _err(
            f"❌ hive-swarm not installed: {e}\n"
            "   `pip install -e ../hive-swarm[langgraph]` from the repo root."
        )
        raise typer.Exit(2)

    # If --tenant given, set the env so any QuotaTracker constructed inside the
    # swarm graph picks it up automatically.
    if tenant:
        os.environ["AI_PROVIDER_GATEWAY_TENANT"] = tenant

    # Auto-detect TTY for interactive HITL if --interactive not explicit
    interactive_resolved = interactive or (sys.stdin.isatty() and not auto_approve)

    try:
        config_kwargs: dict[str, Any] = {
            "topology": topology,
            "consensus_protocol": consensus,
            "max_agents": max_agents,
            "sona_enabled": sona,
            "llm_backend": backend,
            "llm_default_provider": provider,
            "llm_max_tokens": max_tokens,
            "llm_temperature": temperature,
            "anti_drift_mode": anti_drift_mode,
            "llm_stream_enabled": stream,
            "cost_tracking_enabled": not no_cost,
        }
        if model:
            config_kwargs["llm_default_model"] = model
        if auto_approve and not interactive_resolved:
            config_kwargs["require_approval_above_risk"] = 0.99
        config = SwarmConfig(**config_kwargs)
    except Exception as e:
        _err(f"❌ SwarmConfig rejected: {e}")
        raise typer.Exit(2)

    swarm_id = thread_id or f"cli-{uuid.uuid4().hex[:12]}"
    state = SwarmState(swarm_id=swarm_id, objective=prompt, config=config)

    try:
        graph = build_swarm_graph(config)
    except Exception as e:
        _err(f"❌ build_swarm_graph failed: {e}")
        raise typer.Exit(2)

    invoke_config = {"configurable": {"thread_id": swarm_id}}

    # ── First invocation ──────────────────────────────────────────────────
    try:
        result = graph.invoke(state.to_json_dict(), config=invoke_config)
    except Exception as e:
        _err(f"❌ swarm invocation failed: {e}")
        raise typer.Exit(3)

    final = SwarmState.from_json_dict(result)

    # ── Interactive HITL loop ──────────────────────────────────────────────
    if interactive_resolved:
        # Look for the most recent approval_request payload in history
        max_hitl_rounds = 3
        rounds = 0
        while final.status == "awaiting_approval" and rounds < max_hitl_rounds:
            rounds += 1
            # Synthesize the prompt payload from final.consensus_result
            cr = final.consensus_result
            payload = {
                "swarm_id": final.swarm_id,
                "proposed_action_preview": (
                    (cr.action[:1500] + "…")
                    if cr and cr.action and len(cr.action) > 1500
                    else (cr.action if cr else "")
                ),
                "risk_score": cr.risk_score if cr else None,
                "agreement_fraction": cr.agreement_fraction if cr else None,
                "protocol": cr.protocol if cr else "",
                "decision_token_required": final.approval_decision_token,
            }
            decision = _interactive_hitl_prompt(final.swarm_id, payload)
            if decision is None:
                _err("HITL: invalid response, treating as deny.")
                decision = {
                    "decision": "deny",
                    "reviewer_id": "cli",
                    "decision_token": final.approval_decision_token,
                }
            try:
                result = graph.invoke(Command(resume=decision), config=invoke_config)
                final = SwarmState.from_json_dict(result)
            except Exception as e:
                _err(f"❌ swarm resume failed: {e}")
                raise typer.Exit(3)

    # ── Output ────────────────────────────────────────────────────────────

    total_in = sum((r.usage.input_tokens if r.usage else 0) for r in final.worker_results)
    total_out = sum((r.usage.output_tokens if r.usage else 0) for r in final.worker_results)
    total_cost = sum(
        (r.usage.cost_usd if (r.usage and r.usage.cost_usd is not None) else 0.0)
        for r in final.worker_results
    )
    cost_known = any(r.usage and r.usage.cost_usd is not None for r in final.worker_results)

    payload = {
        "swarm_id": final.swarm_id,
        "objective_hash": final.objective_hash,
        "status": final.status,
        "failure_cause": final.failure_cause,
        "iterations": final.iteration,
        "sona_cycles": final.sona_cycle_count,
        "topology": topology,
        "consensus": consensus,
        "backend": backend,
        "provider": provider,
        "model": model or "",
        "anti_drift_mode": anti_drift_mode,
        "streamed": stream,
        "tenant": tenant,
        "interactive": interactive_resolved,
        "worker_count": len(final.worker_results),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_cost_usd": round(total_cost, 6) if cost_known else None,
        "final_output": final.final_output,
    }
    if show_workers:
        payload["workers"] = [
            {
                "agent_id": r.agent_id,
                "role": r.agent_role,
                "success": r.success,
                "output_preview": (r.output[:300] + "…") if len(r.output) > 300 else r.output,
                "input_tokens": r.usage.input_tokens if r.usage else 0,
                "output_tokens": r.usage.output_tokens if r.usage else 0,
                "cost_usd": r.usage.cost_usd if r.usage else None,
                "model_id_used": r.usage.model_id_used if r.usage else "",
            }
            for r in final.worker_results
        ]

    if json_output:
        print(json.dumps(payload))
    else:
        if _HAS_RICH and _console:
            _console.rule(f"[bold]swarm[/bold] id={final.swarm_id}")
            _console.print(Panel(_rich_escape(prompt), title="Objective"))
            cost_str = f"${total_cost:.4f}" if cost_known else "—"
            _console.print(
                f"[dim]status[/dim] {final.status}  "
                f"[dim]iter[/dim] {final.iteration}  "
                f"[dim]workers[/dim] {len(final.worker_results)}  "
                f"[dim]tokens[/dim] {total_in}/{total_out}  "
                f"[dim]cost[/dim] {cost_str}"
            )
            if final.final_output:
                _console.print(Panel(_rich_escape(final.final_output), title="Final output"))
            if show_workers:
                t = Table(title="Workers")
                t.add_column("Role")
                t.add_column("OK")
                t.add_column("Tokens (in/out)")
                t.add_column("Cost")
                t.add_column("Output preview")
                for r in final.worker_results:
                    in_t = r.usage.input_tokens if r.usage else 0
                    out_t = r.usage.output_tokens if r.usage else 0
                    cost = (
                        f"${r.usage.cost_usd:.4f}"
                        if (r.usage and r.usage.cost_usd is not None)
                        else "—"
                    )
                    preview = (r.output[:60] + "…") if len(r.output) > 60 else r.output
                    t.add_row(
                        r.agent_role,
                        "✓" if r.success else "✗",
                        f"{in_t}/{out_t}",
                        cost,
                        _rich_escape(preview),
                    )
                _console.print(t)
        else:
            print(f"swarm_id: {final.swarm_id}")
            print(f"status:   {final.status}")
            print(f"workers:  {len(final.worker_results)}")
            print(f"tokens:   {total_in} in / {total_out} out")
            if cost_known:
                print(f"cost:     ${total_cost:.4f}")
            print(f"final:    {final.final_output[:200]}")

    if final.status not in ("completed",):
        raise typer.Exit(4)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
