"""CLI command for database querying, export, and deletion."""
from datetime import datetime
from typing import Optional

import typer

from core.cmd.base import Command
from core.services.db_service import DbService
from core.services.export_service import ExportService
from core.ui.console import console, error, info, success, warn
from core.ui.renderers import (render_db_rows, render_db_rows_web,
                               render_db_summary, render_raw_rows)


class DbCommand(Command):
    """Database management CLI command (query, summarize, delete)."""

    name = "db"
    help = "[bold cyan]Query stored subdomains[/bold cyan] or view a database summary."

    # pylint: disable=arguments-differ,too-many-arguments,too-many-positional-arguments
    def callback(
        self,
        domain: Optional[str] = typer.Option(
            None, "-d", "--domain", help="Target domain. Omit to list all tracked domains."
        ),
        web: bool = typer.Option(
            False,
            "--web",
            help="Show ALIVE, HTTP STATUS, and TITLE columns instead of source/timestamps.",
        ),
        filter_plugin: Optional[str] = typer.Option(
            None, "--filter-plugin", help="Filter results by plugin name."
        ),
        new_since: Optional[str] = typer.Option(
            None, "--new-since", help="Show subdomains first seen after YYYY-MM-DD."
        ),
        delete: bool = typer.Option(
            False, "--delete", help="Delete all records for the target domain."
        ),
        output_n: Optional[str] = typer.Option(
            None, "-oN", help="Save subdomains to file (one per line)."
        ),
        output_x: Optional[str] = typer.Option(
            None,
            "-oX",
            help=(
                "Save subdomains to file with custom separator. "
                "Use -oX '<sep>:<file>' e.g. ' :out.txt' or ';:out.txt'"
            ),
        ),
        raw_query: Optional[str] = typer.Option(
            None,
            "-C",
            "--custom-query",
            help=(
                "Run a raw SELECT query against the DB. "
                "e.g. -C \"SELECT subdomain FROM subdomain WHERE target='x.com'\""
            ),
        ),
    ) -> None:
        self.run_async(
            self._db(
                domain,
                web,
                filter_plugin,
                new_since,
                delete,
                output_n,
                output_x,
                raw_query,
            )
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    async def _db(
        self,
        domain: Optional[str],
        web: bool,
        filter_plugin: Optional[str],
        new_since: Optional[str],
        delete: bool,
        output_n: Optional[str],
        output_x: Optional[str],
        raw_query: Optional[str],
    ) -> None:
        self.show_banner()
        self.setup_logging()

        service = DbService()

        if raw_query:
            await self._db_raw_query(service, raw_query, output_n, output_x)
            return

        if not domain:
            if any([delete, filter_plugin, new_since, output_n, output_x, web]):
                error("Filters and output flags require -d <domain>.")
            await self._db_summary(service)
            return

        if delete:
            if output_n or output_x:
                warn("-oN / -oX are ignored when using --delete.")
            await self._db_delete(service, domain)
            return

        await self._db_query(
            service,
            domain,
            web,
            filter_plugin,
            new_since,
            output_n,
            output_x,
        )

    async def _db_summary(self, service: DbService) -> None:
        summaries = await service.get_summary()
        if not summaries:
            console.print("[dim]  No targets stored in the database yet.[/dim]\n")
            return
        render_db_summary(summaries)

    async def _db_delete(self, service: DbService, domain: str) -> None:
        count = await service.delete_domain(domain)
        if count == 0:
            console.print(
                f"[dim]  No records found for[/dim] "
                f"[bold white]{domain}[/bold white]\n"
            )
        else:
            success(
                f"Deleted [bold white]{count}[/bold white] "
                f"records for [bold white]{domain}[/bold white]"
            )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    async def _db_query(
        self,
        service: DbService,
        domain: str,
        web: bool,
        filter_plugin: Optional[str],
        new_since: Optional[str],
        output_n: Optional[str],
        output_x: Optional[str],
    ) -> None:
        since_dt = None
        if filter_plugin:
            info(
                f"Target : [bold white]{domain}[/bold white]  "
                f"Plugin : [bold white]{filter_plugin}[/bold white]"
            )
        elif new_since:
            try:
                since_dt = datetime.strptime(new_since, "%Y-%m-%d")
            except ValueError:
                error("Invalid date format. Use YYYY-MM-DD.")
            info(
                f"Target : [bold white]{domain}[/bold white]  "
                f"New since : [bold white]{new_since}[/bold white]"
            )
        else:
            info(f"Target : [bold white]{domain}[/bold white]")

        rows = await service.get_subdomains(
            domain, filter_plugin=filter_plugin, new_since=since_dt
        )

        console.print()

        if not rows:
            console.print(
                f"[dim]  No subdomains found for[/dim] "
                f"[bold white]{domain}[/bold white]\n"
            )
            return

        if web:
            render_db_rows_web(rows)
        else:
            render_db_rows(rows)

        console.print(f"\n[dim]  {len(rows)} result(s) for {domain}[/dim]\n")

        subdomains = [row.subdomain for row in rows]

        if output_n:
            ExportService.write_output(subdomains, output_n, separator="\n")

        if output_x:
            sep, file = ExportService.parse_ox(output_x)
            ExportService.write_output(subdomains, file, separator=sep)

    async def _db_raw_query(
        self,
        service: DbService,
        query: str,
        output_n: Optional[str],
        output_x: Optional[str],
    ) -> None:
        q = query.strip()
        if not q.upper().startswith("SELECT"):
            error("Only SELECT queries are allowed with -C.")

        info(f"Query : [dim white]{q}[/dim white]")
        console.print()

        rows = await service.raw_query(q)

        if not rows:
            console.print("[dim]  No results.[/dim]\n")
            return

        render_raw_rows(rows)

        first_col = list(rows[0].keys())[0]
        values = [str(row[first_col]) for row in rows if row.get(first_col) is not None]

        if output_n:
            ExportService.write_output(values, output_n, separator="\n")

        if output_x:
            sep, file = ExportService.parse_ox(output_x)
            ExportService.write_output(values, file, separator=sep)
