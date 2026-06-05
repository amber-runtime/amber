"""amber workflows — query deployed workflow data via the admin dashboard API.

Read-only commands backed by GET /admin/api. Authentication uses the cached
Cognito CLI session (run ``amber admin login`` first). Pass ``--json`` to emit
the raw API response, which is the format coding agents should consume.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Optional

import click
from rich.console import Console
from rich.table import Table

from amber_cli import dashboard_api, dashboard_auth
from amber_cli.config_loader import find_config_path, load_config

console = Console()


def _require_config_path() -> str:
    config_path = find_config_path()
    if not load_config().name or not config_path:
        click.echo("No amber.yaml found. Run 'amber init' first.")
        raise SystemExit(1)
    return config_path


def _context() -> tuple[str, Optional[str]]:
    """Resolve (api_base, token), turning auth/output errors into exit-1 messages."""
    config_path = _require_config_path()
    try:
        return dashboard_api.resolve_context(config_path)
    except (dashboard_api.DashboardAPIError, dashboard_auth.DashboardAuthError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)


def _run(fetch) -> dict[str, Any]:
    api_base, token = _context()
    try:
        return fetch(api_base, token)
    except (dashboard_api.DashboardAPIError, dashboard_auth.DashboardAuthError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)


def _fmt_ts(value: Any) -> str:
    """Format an epoch-millisecond timestamp as local time, or '-' when missing."""
    if not value:
        return "-"
    try:
        return dt.datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, TypeError):
        return str(value)


@click.group()
def workflows() -> None:
    """Query workflow data for scripts and agents (requires 'amber admin login')."""


@workflows.command("list")
@click.option("--status", default=None, help="Filter by workflow status")
@click.option("--limit", default=50, show_default=True, help="Max rows to return")
@click.option("--offset", default=0, show_default=True, help="Pagination offset")
@click.option("--json", "as_json", is_flag=True, help="Emit raw API JSON")
def list_workflows(status: Optional[str], limit: int, offset: int, as_json: bool) -> None:
    """List workflows."""
    payload = _run(
        lambda base, token: dashboard_api.list_workflows(
            base, token, status=status, limit=limit, offset=offset
        )
    )
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return

    rows = payload.get("workflows", [])
    table = Table(show_header=True, header_style="bold")
    for col in ("Workflow ID", "Name", "Status", "Created", "Completed/Updated", "Attempts"):
        table.add_column(col)
    for wf in rows:
        table.add_row(
            str(wf.get("workflow_id", "")),
            str(wf.get("name", "")),
            str(wf.get("status", "")),
            _fmt_ts(wf.get("created_at")),
            _fmt_ts(wf.get("completed_at")),
            str(wf.get("recovery_attempts") if wf.get("recovery_attempts") is not None else "-"),
        )
    console.print(table)
    if payload.get("has_more"):
        console.print(f"[dim]More results available — use --offset {offset + limit}[/dim]")


@workflows.command("queued")
@click.option("--queue-name", default=None, help="Filter by queue name")
@click.option("--limit", default=50, show_default=True, help="Max rows to return")
@click.option("--offset", default=0, show_default=True, help="Pagination offset")
@click.option("--json", "as_json", is_flag=True, help="Emit raw API JSON")
def queued(queue_name: Optional[str], limit: int, offset: int, as_json: bool) -> None:
    """List queued workflows."""
    payload = _run(
        lambda base, token: dashboard_api.list_queued(
            base, token, queue_name=queue_name, limit=limit, offset=offset
        )
    )
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return

    rows = payload.get("workflows", [])
    table = Table(show_header=True, header_style="bold")
    for col in ("Workflow ID", "Name", "Status", "Queue", "Created", "Attempts"):
        table.add_column(col)
    for wf in rows:
        table.add_row(
            str(wf.get("workflow_id", "")),
            str(wf.get("name", "")),
            str(wf.get("status", "")),
            str(wf.get("queue_name") or "-"),
            _fmt_ts(wf.get("created_at")),
            str(wf.get("recovery_attempts") if wf.get("recovery_attempts") is not None else "-"),
        )
    console.print(table)
    if payload.get("has_more"):
        console.print(f"[dim]More results available — use --offset {offset + limit}[/dim]")


@workflows.command("show")
@click.argument("workflow_id")
@click.option("--json", "as_json", is_flag=True, help="Emit raw API JSON")
def show(workflow_id: str, as_json: bool) -> None:
    """Show a workflow's summary, steps, and events."""
    payload = _run(lambda base, token: dashboard_api.get_workflow(base, token, workflow_id))
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return

    wf = payload.get("workflow", {})
    console.print(f"[bold]{wf.get('name', '')}[/bold]  ({wf.get('workflow_id', '')})")
    console.print(f"  Status:   {wf.get('status', '')}")
    console.print(f"  Created:  {_fmt_ts(wf.get('created_at'))}")
    console.print(f"  Updated:  {_fmt_ts(wf.get('updated_at'))}")
    console.print(f"  Attempts: {wf.get('recovery_attempts', '-')}")
    if wf.get("queue_name"):
        console.print(f"  Queue:    {wf.get('queue_name')}")
    if wf.get("forked_from"):
        console.print(f"  Forked from: {wf.get('forked_from')}")
    if wf.get("output"):
        console.print(f"  Output:   {wf.get('output')}")

    steps = payload.get("steps", [])
    if steps:
        console.print()
        table = Table(show_header=True, header_style="bold", title="Steps")
        for col in ("Step", "Function", "Type", "Status", "Duration (ms)", "Error"):
            table.add_column(col)
        for st in steps:
            table.add_row(
                str(st.get("step_id") if st.get("step_id") is not None else "-"),
                str(st.get("function_name") or "-"),
                str(st.get("event_type", "")),
                str(st.get("status", "")),
                str(st.get("duration_ms") if st.get("duration_ms") is not None else "-"),
                str(st.get("error_message") or ""),
            )
        console.print(table)

    events = payload.get("events", [])
    if events:
        console.print(f"[dim]{len(events)} event(s) — use --json for full detail.[/dim]")
