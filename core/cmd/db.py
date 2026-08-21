"""CLI command for database querying, export, and deletion."""
from datetime import datetime

import typer

from core.cmd.base import Command
from core.services.db_service import DbService
from core.services.export_service import ExportService
from core.ui.console import console, error, info, success, warn
from core.ui.renderers import (
    render_db_rows,
    render_db_rows_dns,
    render_db_rows_web,
    render_db_summary,
    render_raw_rows,
)


class DbCommand(Command):
    """Database management CLI command (query, summarize, delete)."""

    name = "db"
    help = "[bold cyan]Query stored subdomains[/bold cyan] or view a database summary."

    # pylint: disable=arguments-differ,too-many-arguments,too-many-positional-arguments
    def callback(
        self,
        domain: str | None = typer.Option(
            None, "-d", "--domain", help="Target domain. Omit to list all tracked domains."
        ),
        web: bool = typer.Option(
            False,
            "--web",
            help="Show ALIVE, HTTP STATUS, and TITLE columns instead of source/timestamps.",
        ),
        dns: bool = typer.Option(
            False,
            "--dns",
            help="Show DNS resolution results: RESOLVED status and IP ADDRESS columns.",
        ),
        filter_plugin: str | None = typer.Option(
            None, "-P", "--plugin", help="Filter results by plugin name."
        ),
        filter_tech: str | None = typer.Option(
            None, "-t", "--tech", help="Filter results by detected technology (e.g. 'Nginx')."
        ),
        only_alive: bool = typer.Option(
            False, "-a", "--alive", help="Show only verified ALIVE subdomains."
        ),
        only_resolved: bool = typer.Option(
            False, "--resolved", help="Show only subdomains with DNS resolution (has IP)."
        ),
        new_since: str | None = typer.Option(
            None, "--new-since", help="Show subdomains first seen after YYYY-MM-DD."
        ),
        delete: bool = typer.Option(
            False, "--delete", help="Delete all records for the target domain."
        ),
        output: str | None = typer.Option(
            None, "-o", "--out", help="Save subdomains to file (one per line)."
        ),
        output_tech: str | None = typer.Option(
            None,
            "-T",
            "--out-tech",
            help="Save subdomains with detected technologies to file.",
        ),
        export_project: str | None = typer.Option(
            None,
            "--project",
            "-p",
            help="Export plain-text project directory structure for target domain. Optionally specify output directory name (default: 'projects').",
        ),
        raw_query: str | None = typer.Option(
            None,
            "-q",
            "--query",
            help=(
                "Run a raw SELECT query against the DB. "
                "e.g. -q \"SELECT subdomain FROM subdomain WHERE target='x.com'\""
            ),
        ),
    ) -> None:
        self.run_async(
            self._db(
                domain,
                web,
                dns,
                filter_plugin,
                filter_tech,
                only_alive,
                only_resolved,
                new_since,
                delete,
                output,
                output_tech,
                export_project,
                raw_query,
            )
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    async def _db(
        self,
        domain: str | None,
        web: bool,
        dns: bool,
        filter_plugin: str | None,
        filter_tech: str | None,
        only_alive: bool,
        only_resolved: bool,
        new_since: str | None,
        delete: bool,
        output: str | None,
        output_tech: str | None,
        export_project: str | None,
        raw_query: str | None,
    ) -> None:
        self.show_banner()
        self.setup_logging()

        service = DbService()

        if raw_query:
            await self._db_raw_query(service, raw_query, output)
            return

        if not domain:
            if any([delete, filter_plugin, filter_tech, only_alive, only_resolved, new_since, output, output_tech, export_project, web, dns]):
                error("Filters and output flags require -d <domain>.")
            await self._db_summary(service)
            return

        if delete:
            if output or output_tech or export_project is not None:
                warn("--out / --out-tech / --project are ignored when using --delete.")
            await self._db_delete(service, domain)
            return

        await self._db_query(
            service,
            domain,
            web,
            dns,
            filter_plugin,
            filter_tech,
            only_alive,
            only_resolved,
            new_since,
            output,
            output_tech,
            export_project,
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
        dns: bool,
        filter_plugin: str | None,
        filter_tech: str | None,
        only_alive: bool,
        only_resolved: bool,
        new_since: str | None,
        output: str | None,
        output_tech: str | None,
        export_project: str | None,
    ) -> None:
        since_dt = None
        filters_str = []
        if filter_plugin:
            filters_str.append(f"Plugin : [bold white]{filter_plugin}[/bold white]")
        if filter_tech:
            filters_str.append(f"Tech : [bold white]{filter_tech}[/bold white]")
        if only_alive:
            filters_str.append("Filter : [bold green]Alive only[/bold green]")
        if only_resolved:
            filters_str.append("Filter : [bold green]Resolved only[/bold green]")
        if new_since:
            try:
                since_dt = datetime.strptime(new_since, "%Y-%m-%d")
            except ValueError:
                error("Invalid date format. Use YYYY-MM-DD.")
            filters_str.append(f"New since : [bold white]{new_since}[/bold white]")

        info_msg = f"Target : [bold white]{domain}[/bold white]"
        if filters_str:
            info_msg += "  " + "  ".join(filters_str)
        info(info_msg)

        rows = await service.get_subdomains(
            domain,
            filter_plugin=filter_plugin,
            filter_tech=filter_tech,
            new_since=since_dt,
            only_alive=only_alive,
            only_dead=False,
        )

        # Apply DNS resolution filters in-memory (ip column)
        if only_resolved:
            rows = [r for r in rows if getattr(r, "ip", None)]

        console.print()

        if not rows:
            console.print(
                f"[dim]  No subdomains found for[/dim] "
                f"[bold white]{domain}[/bold white]\n"
            )
            return

        if dns:
            render_db_rows_dns(rows)
        elif web:
            render_db_rows_web(rows)
        else:
            render_db_rows(rows)

        console.print(f"\n[dim]  {len(rows)} result(s) for {domain}[/dim]\n")

        subdomains = [row.subdomain for row in rows]

        if output:
            ExportService.write_output(subdomains, output, separator="\n")

        if output_tech:
            from core.ui.renderers import _format_tech
            tech_lines = [
                f"{row.subdomain} [{_format_tech(getattr(row, 'tech', None))}]"
                for row in rows
            ]
            ExportService.write_output(tech_lines, output_tech, separator="\n")

        if export_project is not None:
            from core.services.project_service import ProjectService
            from core.ui.renderers import render_project_summary
            out_dir = export_project if export_project else "projects"
            proj_service = ProjectService()
            summary = await proj_service.export_project(domain, out_dir=out_dir)
            render_project_summary(summary)

    async def _db_raw_query(
        self,
        service: DbService,
        query: str,
        output: str | None,
    ) -> None:
        q = query.strip()
        if not q.upper().startswith("SELECT"):
            error("Only SELECT queries are allowed with -q.")

        info(f"Query : [dim white]{q}[/dim white]")
        console.print()

        rows = await service.raw_query(q)

        if not rows:
            console.print("[dim]  No results.[/dim]\n")
            return

        render_raw_rows(rows)

        first_col = list(rows[0].keys())[0]
        values = [str(row[first_col]) for row in rows if row.get(first_col) is not None]

        if output:
            ExportService.write_output(values, output, separator="\n")
