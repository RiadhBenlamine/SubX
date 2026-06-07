import asyncio
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from core.config_manager import ConfigManager
from core.plugin_manager import PluginManager
from core.processor import Processor
from core.storage_manager import StorageManager
from core.logger import setup_logger

# ------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------

HELP_NAMES = {"help_option_names": ["-h", "--help"]}

app = typer.Typer(
    name="subx",
    help="[bold cyan]SUBX[/bold cyan] — Subdomain Recon Framework",
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings=HELP_NAMES,
)

console = Console()

# ------------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------------

def _banner():
    console.print(Panel.fit(
        Text.assemble(
            ("░██████╗██╗░░░██╗██████╗░██╗░░██╗\n", "bold cyan"),
            ("██╔════╝██║░░░██║██╔══██╗╚██╗██╔╝\n", "bold cyan"),
            ("╚█████╗░██║░░░██║██████╦╝░╚███╔╝░\n", "bold cyan"),
            ("░╚═══██╗██║░░░██║██╔══██╗░██╔██╗░\n", "bold cyan"),
            ("██████╔╝╚██████╔╝██████╦╝██╔╝╚██╗\n", "bold cyan"),
            ("╚═════╝░░╚═════╝░╚═════╝░╚═╝░░╚═╝\n", "bold cyan"),
            ("        subdomain recon framework  ", "dim white"),
        ),
        border_style="cyan",
        padding=(0, 2),
    ))


def _error(msg: str):
    console.print(f"[bold red]  ✘[/bold red]  {msg}")
    raise typer.Exit(1)


def _info(msg: str):
    console.print(f"[bold cyan]  ›[/bold cyan]  {msg}")


def _render_subdomains(rows, title: str = "RESULTS"):
    table = Table(
        title=title,
        box=box.SIMPLE_HEAD,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("SUBDOMAIN", style="white", no_wrap=True)
    table.add_column("SOURCE", style="dim cyan", justify="center")
    table.add_column("FIRST SEEN", style="dim white", justify="right", no_wrap=True)
    table.add_column("LAST SEEN", style="dim white", justify="right", no_wrap=True)

    for row in rows:
        table.add_row(
            row.subdomain,
            row.source_plugin,
            row.first_seen.strftime("%Y-%m-%d %H:%M"),
            row.last_seen.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)
    console.print(f"\n[dim]  {len(rows)} result(s)[/dim]\n")


def _render_enum_results(processed, new_count: int, save: bool):
    table = Table(
        box=box.SIMPLE_HEAD,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 2),
    )
    table.add_column("SUBDOMAIN", style="white", no_wrap=True)
    table.add_column("SOURCE", style="dim cyan", justify="right")

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
        summary.add_row("[Wildcards re-scanned]", str(len(processed.wildcards)))

    summary.add_row("──────────────────", "──────")
    summary.add_row("Total unique", str(processed.total))

    if save:
        summary.add_row("New this run", f"[bold green]{new_count}[/bold green]")

    console.print(Panel(summary, title="[bold cyan]Summary[/bold cyan]", border_style="cyan"))


# ------------------------------------------------------------------
# subx enum -c config.yaml
# ------------------------------------------------------------------

@app.command("enum", context_settings=HELP_NAMES)
def enum(
    config_file: str = typer.Option(..., "-c", "--config", help="Path to YAML/JSON config file."),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to database."),
):
    """[bold cyan]Enumerate subdomains[/bold cyan] for a target domain."""
    asyncio.run(_enum(config_file, save))


async def _enum(config_file: str, save: bool):
    _banner()
    setup_logger()

    try:
        config = ConfigManager(config_path=config_file)
    except FileNotFoundError:
        _error(f"Config file not found: {config_file}")
    except Exception as e:
        _error(f"Failed to load config: {e}")

    if not config.get_target():
        _error("No target defined. Add 'target: example.com' to your config file.")

    target = config.get_target()
    scope  = config.get_scope()

    _info(f"Target  : [bold white]{target}[/bold white]")
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

    processor = Processor(target=target, scope=scope, out_of_scope=config.get_out_of_scope())

    with console.status("[cyan]Running plugins...[/cyan]", spinner="dots"):
        raw_results = await pm.execute_plugins(target)

    processed = processor.process(raw_results)

    if processor.has_wildcards(processed):
        wc_domains = processor.extract_wildcard_domains(processed)
        console.print(f"\n[bold yellow]  ⚡ Wildcards found:[/bold yellow] {', '.join(wc_domains)}")

        with console.status("[yellow]Re-scanning wildcard domains...[/yellow]", spinner="dots"):
            wc_results_all = await asyncio.gather(*[
                pm.execute_plugins(wc) for wc in wc_domains
            ])

        for wc_raw in wc_results_all:
            processed = processor.merge(processed, processor.process(wc_raw))

    new_count = 0
    if save:
        storage = StorageManager()
        await storage.init()
        with console.status("[cyan]Saving to database...[/cyan]", spinner="dots"):
            new_count = await storage.save(processed)
        await storage.close()

    console.print()
    _render_enum_results(processed, new_count, save)


# ------------------------------------------------------------------
# subx db
# subx db -d <domain>
# subx db -d <domain> --filter-plugin <plugin>
# subx db -d <domain> --new-since <YYYY-MM-DD>
# ------------------------------------------------------------------

@app.command("db", context_settings=HELP_NAMES)
def db(
    domain: Optional[str] = typer.Option(None, "-d", "--domain", help="Target domain to query. Omit to list all tracked domains."),
    filter_plugin: Optional[str] = typer.Option(None, "--filter-plugin", help="Filter results by plugin name."),
    new_since: Optional[str] = typer.Option(None, "--new-since", help="Show subdomains first seen after date (YYYY-MM-DD)."),
):
    """[bold cyan]Query stored subdomains[/bold cyan] or view a database summary."""
    asyncio.run(_db_query(domain, filter_plugin, new_since))


async def _db_query(
    domain: Optional[str],
    filter_plugin: Optional[str],
    new_since: Optional[str],
):
    _banner()

    storage = StorageManager()
    await storage.init()

    # No domain — show summary of all tracked targets
    if not domain:
        summaries = await storage.get_targets_summary()
        await storage.close()

        if not summaries:
            console.print("[dim]  No targets stored in the database yet.[/dim]\n")
            return

        table = Table(
            title="DATABASE SUMMARY",
            box=box.SIMPLE_HEAD,
            border_style="cyan",
            header_style="bold cyan",
            show_lines=False,
            padding=(0, 2),
        )
        table.add_column("TARGET DOMAIN", style="white", no_wrap=True)
        table.add_column("SUBDOMAINS", style="green", justify="right")
        table.add_column("LAST UPDATED", style="dim white", justify="right", no_wrap=True)

        for s in summaries:
            last_updated = (
                s["last_updated"].strftime("%Y-%m-%d %H:%M")
                if s["last_updated"] else "Never"
            )
            table.add_row(s["target"], str(s["count"]), last_updated)

        console.print(table)
        console.print(f"\n[dim]  {len(summaries)} target(s) tracked.[/dim]\n")
        return

    # Domain provided — query with optional filters
    if filter_plugin:
        rows = await storage.get_by_plugin(domain, filter_plugin)
        _info(f"Target : [bold white]{domain}[/bold white]  Plugin : [bold white]{filter_plugin}[/bold white]")

    elif new_since:
        try:
            since_dt = datetime.strptime(new_since, "%Y-%m-%d")
        except ValueError:
            await storage.close()
            _error("Invalid date format. Use YYYY-MM-DD.")
            return
        rows = await storage.get_new_since(domain, since_dt)
        _info(f"Target : [bold white]{domain}[/bold white]  New since : [bold white]{new_since}[/bold white]")

    else:
        rows = await storage.get_all(domain)
        _info(f"Target : [bold white]{domain}[/bold white]")

    await storage.close()
    console.print()

    if not rows:
        console.print(f"[dim]  No subdomains found for[/dim] [bold white]{domain}[/bold white]\n")
        return

    _render_subdomains(rows)


# ------------------------------------------------------------------
# Entry
# ------------------------------------------------------------------

if __name__ == "__main__":
    app()