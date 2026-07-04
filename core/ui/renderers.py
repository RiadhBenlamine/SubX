from rich import box
from rich.panel import Panel
from rich.table import Table

from core.models import ProcessedResult
from core.ui.console import console, make_table


def render_db_summary(summaries: list[dict]) -> None:
    table = make_table(
        ("TARGET DOMAIN", {"style": "white",    "no_wrap": True}),
        ("SUBDOMAINS",    {"style": "green",     "justify": "right"}),
        ("LAST UPDATED",  {"style": "dim white", "justify": "right", "no_wrap": True}),
    )
    table.title = "DATABASE SUMMARY"
    for s in summaries:
        last_updated = (
            s["last_updated"].strftime("%Y-%m-%d %H:%M")
            if s["last_updated"] else "—"
        )
        table.add_row(s["target"], str(s["count"]), last_updated)
    console.print(table)
    console.print(f"\n[dim]  {len(summaries)} target(s) tracked.[/dim]\n")


def render_db_rows(rows: list, domain: str) -> None:
    table = make_table(
        ("SUBDOMAIN",  {"style": "white",     "no_wrap": True}),
        ("SOURCE",     {"style": "dim cyan",  "justify": "center"}),
        ("FIRST SEEN", {"style": "dim white", "justify": "right", "no_wrap": True}),
        ("LAST SEEN",  {"style": "dim white", "justify": "right", "no_wrap": True}),
    )
    for row in rows:
        table.add_row(
            row.subdomain,
            row.source_plugin,
            row.first_seen.strftime("%Y-%m-%d %H:%M"),
            row.last_seen.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


def render_db_rows_web(rows: list, domain: str) -> None:
    table = make_table(
        ("SUBDOMAIN", {"style": "white"}),
        ("ALIVE",     {"style": "white",     "justify": "center"}),
        ("STATUS",    {"style": "green",     "justify": "right"}),
        ("TITLE",     {"style": "dim white", "no_wrap": True, "overflow": "ellipsis"}),
    )
    for row in rows:
        if row.alive is True:
            alive_str = "[bold green]✔[/bold green]"
        elif row.alive is False:
            alive_str = "[bold red]✘[/bold red]"
        else:
            alive_str = "[dim]?[/dim]"
        status_str = str(row.status_code) if row.status_code is not None else "—"
        title_str = row.title if row.title else "—"
        table.add_row(
            row.subdomain,
            alive_str,
            status_str,
            title_str,
        )
    console.print(table)


def render_raw_rows(rows: list[dict]) -> None:
    if not rows:
        console.print("[dim]  No results.[/dim]\n")
        return

    columns = list(rows[0].keys())
    table = make_table(*[(col.upper(), {"style": "white", "no_wrap": True}) for col in columns])

    for row in rows:
        table.add_row(*[str(v) if v is not None else "—" for v in row.values()])

    console.print(table)
    console.print(f"\n[dim]  {len(rows)} row(s) returned.[/dim]\n")


def render_enum_results(
    processed_by_target: dict[str, dict],
    save: bool,
) -> None:
    for target, data in processed_by_target.items():
        processed: ProcessedResult = data["processed"]
        new_count: int = data["new_count"]

        console.print(f"\n[bold cyan]─── {target} ───[/bold cyan]")

        table = make_table(
            ("SUBDOMAIN", {"style": "white",    "no_wrap": True}),
            ("SOURCE",    {"style": "dim cyan", "justify": "right"}),
        )
        for plugin_name, subs in processed.by_plugin.items():
            for sub in subs:
                table.add_row(sub, plugin_name)
        console.print(table)
        console.print()

        summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        summary.add_column(style="dim white")
        summary.add_column(style="bold white")

        for plugin_name, subs in processed.by_plugin.items():
            summary.add_row(f"[{plugin_name}]", str(len(subs)))

        if processed.wildcards:
            summary.add_row("[wildcards re-scanned]", str(len(processed.wildcards)))

        summary.add_row("──────────────────", "──────")
        summary.add_row("Total unique", str(processed.total))

        if save:
            summary.add_row("New this run", f"[bold green]{new_count}[/bold green]")

        console.print(Panel(
            summary,
            title=f"[bold cyan]Summary — {target}[/bold cyan]",
            border_style="cyan",
        ))


def render_http_probe_summary(rows: list, domain: str) -> None:
    alive = [r for r in rows if r.alive is True]
    dead = [r for r in rows if r.alive is False]
    unchecked = [r for r in rows if r.alive is None]

    table = make_table(
        ("SUBDOMAIN",    {"style": "white",    "no_wrap": True}),
        ("ALIVE",        {"style": "white",    "justify": "center"}),
        ("STATUS",       {"style": "green",    "justify": "right"}),
        ("TITLE",        {"style": "dim white", "overflow": "fold"}),
    )
    for row in alive:
        table.add_row(
            row.subdomain,
            "[bold green]✔[/bold green]",
            str(row.status_code) if row.status_code is not None else "—",
            row.title or "—",
        )
    console.print(table)
    console.print()

    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column(style="dim white")
    summary.add_column(style="bold white")
    summary.add_row("Alive", f"[bold green]{len(alive)}[/bold green]")
    summary.add_row("Dead", f"[bold red]{len(dead)}[/bold red]")
    if unchecked:
        summary.add_row("Unchecked", f"[dim]{len(unchecked)}[/dim]")
    summary.add_row("──────────────────", "──────")
    summary.add_row("Total", str(len(rows)))

    console.print(Panel(
        summary,
        title=f"[bold cyan]Probe Summary — {domain}[/bold cyan]",
        border_style="cyan",
    ))
