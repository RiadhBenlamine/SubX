import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.config_manager import ConfigManager
from tools.httpx import HttpxTool
from core.logger import setup_logger
from core.models import ProcessedResult
from core.plugin_manager import PluginManager
from core.processor import Processor
from core.storage_manager import StorageManager
from core.tool import ToolExecutionError, ToolNotFoundError, ToolTimeoutError
from core.tool_manager import ToolManager

HELP_NAMES = {"help_option_names": ["-h", "--help"]}

app = typer.Typer(
    name="subx",
    help="[bold cyan]SUBX[/bold cyan] — Subdomain Recon Framework",
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings=HELP_NAMES,
)

console = Console()


def _banner() -> None:
    console.print(Panel.fit(
        Text.assemble(
            ("░██████╗██╗░░░██╗██████╗░██╗░░██╗\n", "bold cyan"),
            ("██╔════╝██║░░░██║██╔══██╗╚██╗██╔╝\n", "bold cyan"),
            ("╚█████╗░██║░░░██║██████╦╝░╚███╔╝░\n", "bold cyan"),
            ("░╚═══██╗██║░░░██║██╔══██╗░██╔██╗░\n", "bold cyan"),
            ("██████╔╝╚██████╔╝██████╦╝██╔╝╚██╗\n", "bold cyan"),
            ("╚═════╝░░╚═════╝░╚═════╝░╚═╝░░╚═╝\n", "bold cyan"),
            ("        subdomain recon framework  ", "dim white"),
            ("\n                        by ",        "dim white"),
            ("rbn0x00",                             "bold cyan"),
        ),
        border_style="cyan",
        padding=(0, 2),
    ))


def _info(msg: str)    -> None: console.print(f"[bold cyan]  ›[/bold cyan]  {msg}")
def _success(msg: str) -> None: console.print(f"[bold green]  ✔[/bold green]  {msg}")
def _warn(msg: str)    -> None: console.print(f"[bold yellow]  ⚡[/bold yellow]  {msg}")

def _error(msg: str) -> None:
    console.print(f"[bold red]  ✘[/bold red]  {msg}")
    raise typer.Exit(1)


def _make_table(*columns: tuple[str, dict]) -> Table:
    table = Table(
        box=box.SIMPLE_HEAD,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 2),
    )
    for header, kwargs in columns:
        table.add_column(header, **kwargs)
    return table


def _render_db_summary(summaries: list[dict]) -> None:
    table = _make_table(
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


def _render_db_rows(rows: list, domain: str) -> None:
    table = _make_table(
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


def _render_db_rows_web(rows: list, domain: str) -> None:
    table = _make_table(
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


def _render_raw_rows(rows: list[dict]) -> None:
    if not rows:
        console.print("[dim]  No results.[/dim]\n")
        return

    columns = list(rows[0].keys())
    table = _make_table(*[(col.upper(), {"style": "white", "no_wrap": True}) for col in columns])

    for row in rows:
        table.add_row(*[str(v) if v is not None else "—" for v in row.values()])

    console.print(table)
    console.print(f"\n[dim]  {len(rows)} row(s) returned.[/dim]\n")


def _render_enum_results(
    processed_by_target: dict[str, dict],
    save: bool,
) -> None:
    for target, data in processed_by_target.items():
        processed: ProcessedResult = data["processed"]
        new_count: int = data["new_count"]

        console.print(f"\n[bold cyan]─── {target} ───[/bold cyan]")

        table = _make_table(
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


def _render_http_probe_summary(rows: list, domain: str) -> None:
    alive = [r for r in rows if r.alive is True]
    dead = [r for r in rows if r.alive is False]
    unchecked = [r for r in rows if r.alive is None]

    table = _make_table(
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


def _write_output(values: list[str], output: str, separator: str = "\n") -> None:
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    sep = separator.replace("\\n", "\n").replace("\\t", "\t")
    out.write_text(sep.join(values) + "\n")
    _success(
        f"Saved [bold white]{len(values)}[/bold white] entries → "
        f"[bold white]{output}[/bold white]  "
        f"[dim](sep: {repr(sep)})[/dim]"
    )


@app.command("enum", context_settings=HELP_NAMES)
def enum(
    config_file: str = typer.Option(..., "-c", "--config", help="Path to YAML/JSON config file."),
    save: bool       = typer.Option(True, "--save/--no-save", help="Save results to database."),
) -> None:
    """[bold cyan]Enumerate subdomains[/bold cyan] for target domain(s)."""
    asyncio.run(_enum(config_file, save))


async def _enum(config_file: str, save: bool) -> None:
    _banner()
    setup_logger()

    try:
        config = ConfigManager(config_path=config_file)
    except (FileNotFoundError, ValueError) as e:
        _error(str(e))
    except Exception as e:
        _error(f"Failed to load config: {e}")

    scope = config.get_scope()

    _info(f"Scope   : [bold white]{', '.join(scope)}[/bold white]")
    if config.get_out_of_scope():
        _info(f"OOS     : [bold white]{', '.join(config.get_out_of_scope())}[/bold white]")
    if config.get_sources():
        _info(f"Sources : [bold white]{', '.join(config.get_sources())}[/bold white]")
    console.print()

    pm = PluginManager(config.get_api_keys())
    pm.load_plugins(allowed=config.get_sources())

    if not pm.loaded_plugins:
        _error("No plugins loaded. Check your API keys or sources in config.")

    _info(f"Plugins : [bold white]{', '.join(p.__class__.__name__ for p in pm.loaded_plugins)}[/bold white]")
    console.print()

    processor = Processor(scope=scope, out_of_scope=config.get_out_of_scope())

    storage = None
    if save:
        storage = StorageManager()
        await storage.init()

    # Run all domains concurrently
    domain_results = await asyncio.gather(
        *(_run_domain(pm, processor, domain) for domain in scope)
    )

    processed_by_target: dict[str, dict] = {}
    for domain, processed in zip(scope, domain_results):
        new_count = 0
        if storage:
            with console.status(f"[cyan]Saving {domain}...[/cyan]", spinner="dots"):
                new_count = await storage.save(processed, target=domain)
        processed_by_target[domain] = {"processed": processed, "new_count": new_count}

    if storage:
        await storage.close()

    console.print()
    _render_enum_results(processed_by_target, save)


async def _run_domain(
    pm: PluginManager,
    processor: Processor,
    domain: str,
) -> ProcessedResult:
    with console.status(f"[cyan]Running plugins for {domain}...[/cyan]", spinner="dots"):
        raw = await pm.execute_plugins(domain)

    processed = processor.process(raw)

    if not processor.has_wildcards(processed):
        return processed

    wc_domains = processor.extract_wildcard_domains(processed)
    _warn(f"Wildcards found for {domain}: {', '.join(wc_domains)}")

    with console.status("[yellow]Re-scanning wildcard domains...[/yellow]", spinner="dots"):
        wc_batches = await asyncio.gather(*(pm.execute_plugins(wc) for wc in wc_domains))

    for wc_raw in wc_batches:
        processed = processor.merge(processed, processor.process(wc_raw))

    return processed


@app.command("http-probe", context_settings=HELP_NAMES)
def http_probe(
    domain: str            = typer.Option(..., "-d", "--domain", help="Target domain to probe stored subdomains for."),
    output_n: Optional[str] = typer.Option(None, "-oN", help="Save alive subdomains to file (one per line)."),
    output_x: Optional[str] = typer.Option(None, "-oX", help="Save alive subdomains to file with custom separator. Use -oX '<sep>:<file>'."),
) -> None:
    """\
    [bold cyan]Probe stored subdomains[/bold cyan] for liveness using httpx.

    Reads every subdomain already stored for the target domain, runs them
    through httpx, and persists alive/dead status, HTTP status code, and
    page title back into the database.

    \b
    Examples:
      subx http-probe -d telekom.de                       # probe and show results
      subx http-probe -d telekom.de -oN alive.txt          # also save alive hosts
      subx http-probe -d telekom.de -oX ';:alive.txt'      # custom separator
    """
    asyncio.run(_http_probe(domain, output_n, output_x))


async def _http_probe(domain: str, output_n: Optional[str], output_x: Optional[str]) -> None:
    _banner()
    setup_logger()

    _info(f"Target : [bold white]{domain}[/bold white]")
    console.print()

    tool_manager = ToolManager()

    try:
        with console.status(f"[cyan]Probing {domain}...[/cyan]", spinner="dots"):
            results = await tool_manager.run_tool(HttpxTool(), domain)
    except ToolNotFoundError:
        _error("httpx binary not found. Install it (go install / apt) or check your bin/ path.")
        return
    except ToolTimeoutError:
        _error(f"httpx timed out while probing {domain}. Try again or raise the timeout.")
        return
    except ToolExecutionError as e:
        _error(f"httpx failed: {e}")
        return

    if not results:
        console.print(f"[dim]  No subdomains stored for[/dim] [bold white]{domain}[/bold white] [dim]— run `subx enum` first.[/dim]\n")
        return

    # ToolManager already persisted the normalized results, so open a
    # fresh storage handle to read back the now-updated rows.
    storage = StorageManager()
    await storage.init()
    try:
        rows = await storage.get_all(domain)
    finally:
        await storage.close()

    console.print()
    _render_http_probe_summary(rows, domain)

    if output_n or output_x:
        alive_subs = [row.subdomain for row in rows if row.alive is True]
        if not alive_subs:
            _warn("No alive subdomains to write.")
        else:
            if output_n:
                _write_output(alive_subs, output_n, separator="\n")
            if output_x:
                sep, file = _parse_ox(output_x)
                _write_output(alive_subs, file, separator=sep)


@app.command("db", context_settings=HELP_NAMES)
def db(
    domain:        Optional[str] = typer.Option(None,  "-d", "--domain",       help="Target domain. Omit to list all tracked domains."),
    web:           bool          = typer.Option(False, "--web",                help="Show ALIVE, HTTP STATUS, and TITLE columns instead of source/timestamps."),
    filter_plugin: Optional[str] = typer.Option(None,  "--filter-plugin",       help="Filter results by plugin name."),
    new_since:     Optional[str] = typer.Option(None,  "--new-since",           help="Show subdomains first seen after YYYY-MM-DD."),
    delete:        bool          = typer.Option(False, "--delete",               help="Delete all records for the target domain."),
    output_n:      Optional[str] = typer.Option(None,  "-oN",                   help="Save subdomains to file (one per line)."),
    output_x:      Optional[str] = typer.Option(None,  "-oX",                   help="Save subdomains to file with custom separator. Use -oX '<sep>:<file>' e.g. ' :out.txt' or ';:out.txt'"),
    raw_query:     Optional[str] = typer.Option(None,  "-C", "--custom-query",  help="Run a raw SELECT query against the DB. e.g. -C \"SELECT subdomain FROM subdomain WHERE target='x.com'\""),
) -> None:
    """\
    [bold cyan]Query stored subdomains[/bold cyan] or view a database summary.

    \b
    Examples:
      subx db                                          # summary of all targets
      subx db -d telekom.de                            # list all subdomains
      subx db -d telekom.de --web                      # show alive/status/title (needs `subx http-probe` run first)
      subx db -d telekom.de -oN subs.txt               # save one per line
      subx db -d telekom.de -oX ';:subs.txt'           # save semicolon-separated
      subx db -d telekom.de -oX ' :subs.txt'           # save space-separated
      subx db -d telekom.de --filter-plugin ViewDns    # filter by plugin
      subx db -d telekom.de --new-since 2025-06-01     # new since date
      subx db -C "SELECT subdomain FROM subdomain WHERE target='telekom.de' LIMIT 10"
      subx db -C "SELECT ..." -oX ';:out.txt'          # query + custom output
    """
    asyncio.run(_db(domain, web, filter_plugin, new_since, delete, output_n, output_x, raw_query))


@app.command("dev-migrate", context_settings=HELP_NAMES)
def db_migrate(
    no_backup: bool = typer.Option(False, "--no-backup", help="Skip creating a backup before migrating."),
) -> None:
    """
    [bold cyan]Safely migrate the database schema[/bold cyan] to match the current models.


    Adds any new columns that exist in the code but are missing from the DB.
    A timestamped backup of the database file is created before any changes.

    Examples:
      subx dev-migrate                 # migrate with backup
      subx dev-migrate --no-backup     # migrate without backup
    """
    asyncio.run(_db_migrate(backup=not no_backup))


async def _db_migrate(backup: bool) -> None:
    _banner()
    storage = StorageManager()
    try:
        added = await storage.migrate(backup=backup)
    except Exception as e:
        _error(f"Migration failed: {e}")
    finally:
        await storage.close()

    if added:
        _success(f"Migration complete — added [bold white]{len(added)}[/bold white] column(s):")
        for col in added:
            console.print(f"  [dim]•[/dim]  [bold white]{col}[/bold white]")
    else:
        _info("Database schema is already up to date. No changes needed.")

    console.print()


async def _db(
    domain: Optional[str],
    web: bool,
    filter_plugin: Optional[str],
    new_since: Optional[str],
    delete: bool,
    output_n: Optional[str],
    output_x: Optional[str],
    raw_query: Optional[str],
) -> None:
    _banner()
    storage = StorageManager()
    await storage.init()
    try:
        await _db_dispatch(storage, domain, web, filter_plugin, new_since, delete, output_n, output_x, raw_query)
    finally:
        await storage.close()


async def _db_dispatch(
    storage: StorageManager,
    domain: Optional[str],
    web: bool,
    filter_plugin: Optional[str],
    new_since: Optional[str],
    delete: bool,
    output_n: Optional[str],
    output_x: Optional[str],
    raw_query: Optional[str],
) -> None:
    if raw_query:
        await _db_raw_query(storage, raw_query, output_n, output_x)
        return

    if not domain:
        if any([delete, filter_plugin, new_since, output_n, output_x, web]):
            _error("Filters and output flags require -d <domain>.")
        await _db_summary(storage)
        return

    if delete:
        if output_n or output_x:
            _warn("-oN / -oX are ignored when using --delete.")
        await _db_delete(storage, domain)
        return

    await _db_query(storage, domain, web, filter_plugin, new_since, output_n, output_x)


async def _db_summary(storage: StorageManager) -> None:
    summaries = await storage.get_targets_summary()
    if not summaries:
        console.print("[dim]  No targets stored in the database yet.[/dim]\n")
        return
    _render_db_summary(summaries)


async def _db_delete(storage: StorageManager, domain: str) -> None:
    count = await storage.delete(domain)
    if count == 0:
        console.print(f"[dim]  No records found for[/dim] [bold white]{domain}[/bold white]\n")
    else:
        _success(f"Deleted [bold white]{count}[/bold white] records for [bold white]{domain}[/bold white]")


async def _db_query(
    storage: StorageManager,
    domain: str,
    web: bool,
    filter_plugin: Optional[str],
    new_since: Optional[str],
    output_n: Optional[str],
    output_x: Optional[str],
) -> None:
    if filter_plugin:
        rows = await storage.get_by_plugin(domain, filter_plugin)
        _info(f"Target : [bold white]{domain}[/bold white]  Plugin : [bold white]{filter_plugin}[/bold white]")

    elif new_since:
        try:
            since_dt = datetime.strptime(new_since, "%Y-%m-%d")
        except ValueError:
            _error("Invalid date format. Use YYYY-MM-DD.")
            return
        rows = await storage.get_new_since(domain, since_dt)
        _info(f"Target : [bold white]{domain}[/bold white]  New since : [bold white]{new_since}[/bold white]")

    else:
        rows = await storage.get_all(domain)
        _info(f"Target : [bold white]{domain}[/bold white]")

    console.print()

    if not rows:
        console.print(f"[dim]  No subdomains found for[/dim] [bold white]{domain}[/bold white]\n")
        return

    if web:
        _render_db_rows_web(rows, domain)
    else:
        _render_db_rows(rows, domain)

    console.print(f"\n[dim]  {len(rows)} result(s) for {domain}[/dim]\n")

    subdomains = [row.subdomain for row in rows]

    if output_n:
        _write_output(subdomains, output_n, separator="\n")

    if output_x:
        sep, file = _parse_ox(output_x)
        _write_output(subdomains, file, separator=sep)


async def _db_raw_query(
    storage: StorageManager,
    query: str,
    output_n: Optional[str],
    output_x: Optional[str],
) -> None:
    q = query.strip()
    if not q.upper().startswith("SELECT"):
        _error("Only SELECT queries are allowed with -C.")

    _info(f"Query : [dim white]{q}[/dim white]")
    console.print()

    rows = await storage.raw_query(q)

    if not rows:
        console.print("[dim]  No results.[/dim]\n")
        return

    _render_raw_rows(rows)

    first_col = list(rows[0].keys())[0]
    values = [str(row[first_col]) for row in rows if row.get(first_col) is not None]

    if output_n:
        _write_output(values, output_n, separator="\n")

    if output_x:
        sep, file = _parse_ox(output_x)
        _write_output(values, file, separator=sep)


def _parse_ox(value: str) -> tuple[str, str]:
    idx = value.rfind(":")
    if idx == -1 or idx == len(value) - 1:
        _error(
            "-oX format is '<separator>:<file>'  e.g.  ';:out.txt'  or  ' :out.txt'\n"
            "  The separator comes before the last colon, the file path after it."
        )
    sep = value[:idx]
    file = value[idx + 1:]
    return sep, file


if __name__ == "__main__":
    app()