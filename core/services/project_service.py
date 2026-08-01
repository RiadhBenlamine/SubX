"""Service layer for managing target project directories and plain-text recon exports."""
import logging
from pathlib import Path
from typing import NamedTuple

from core.db_models import Subdomain
from core.services.base import Service
from core.ui.renderers import _format_tech

logger = logging.getLogger(__name__)


class ProjectSummary(NamedTuple):
    target: str
    project_dir: Path
    recon_dir: Path
    files_created: dict[str, int]


class ProjectService(Service):
    """Orchestrates plain-text project folder layout and data exports for target domains."""

    async def export_project(
        self,
        domain: str,
        out_dir: str = "projects",
    ) -> ProjectSummary:
        """Create/sync plain-text project structure for target domain.

        Directory structure created:
            <out_dir>/<domain>/
                └── recon/
                      ├── subdomains.txt (all discovered subdomains)
                      ├── alive.txt      (subdomains verified alive)
                      ├── dead.txt       (subdomains currently down)
                      ├── techs.txt      (subdomains with tech stack)
                      ├── status.txt     (subdomains with HTTP status & title)
                      ├── ips.txt        (subdomains with IP addresses)
                      └── sources.txt    (subdomains with discovery plugins)

        Returns ProjectSummary with file paths and entry counts.
        """
        async def _export(storage) -> ProjectSummary:
            rows: list[Subdomain] = await storage.get_all(domain)

            project_dir = Path(out_dir) / domain
            recon_dir = project_dir / "recon"
            recon_dir.mkdir(parents=True, exist_ok=True)

            files_created: dict[str, int] = {}

            # 1. subdomains.txt — all subdomains
            all_subs = [r.subdomain for r in rows]
            subdomains_file = recon_dir / "subdomains.txt"
            subdomains_file.write_text(
                "\n".join(all_subs) + ("\n" if all_subs else ""), encoding="utf-8"
            )
            files_created["subdomains.txt"] = len(all_subs)

            # 2. alive.txt — subdomains verified alive
            alive_rows = [r for r in rows if r.alive is True]
            alive_subs = [r.subdomain for r in alive_rows]
            alive_file = recon_dir / "alive.txt"
            alive_file.write_text(
                "\n".join(alive_subs) + ("\n" if alive_subs else ""), encoding="utf-8"
            )
            files_created["alive.txt"] = len(alive_subs)

            # 3. dead.txt — subdomains currently down
            dead_rows = [r for r in rows if r.alive is False]
            dead_subs = [r.subdomain for r in dead_rows]
            dead_file = recon_dir / "dead.txt"
            dead_file.write_text(
                "\n".join(dead_subs) + ("\n" if dead_subs else ""), encoding="utf-8"
            )
            files_created["dead.txt"] = len(dead_subs)

            # 4. techs.txt — subdomains with detected technologies
            tech_rows = [r for r in rows if r.tech]
            tech_lines = [
                f"{r.subdomain} [{_format_tech(r.tech)}]" for r in tech_rows
            ]
            techs_file = recon_dir / "techs.txt"
            techs_file.write_text(
                "\n".join(tech_lines) + ("\n" if tech_lines else ""), encoding="utf-8"
            )
            files_created["techs.txt"] = len(tech_lines)

            # 5. status.txt — HTTP status code and title for probed subdomains
            status_rows = [r for r in rows if r.status_code is not None or r.title]
            status_lines = [
                f"{r.subdomain} [{r.status_code or '—'}] [{r.title or '—'}]"
                for r in status_rows
            ]
            status_file = recon_dir / "status.txt"
            status_file.write_text(
                "\n".join(status_lines) + ("\n" if status_lines else ""), encoding="utf-8"
            )
            files_created["status.txt"] = len(status_lines)

            # 6. ips.txt — subdomains with IP addresses
            ip_rows = [r for r in rows if r.ip]
            ip_lines = [f"{r.subdomain} [{r.ip}]" for r in ip_rows]
            ips_file = recon_dir / "ips.txt"
            ips_file.write_text(
                "\n".join(ip_lines) + ("\n" if ip_lines else ""), encoding="utf-8"
            )
            files_created["ips.txt"] = len(ip_lines)

            # 7. sources.txt — subdomains with discovery sources
            source_lines = []
            for r in rows:
                sources_str = (
                    ", ".join(s.source_plugin for s in r.sources)
                    if getattr(r, "sources", None)
                    else r.source_plugin
                )
                source_lines.append(f"{r.subdomain} [{sources_str}]")
            sources_file = recon_dir / "sources.txt"
            sources_file.write_text(
                "\n".join(source_lines) + ("\n" if source_lines else ""), encoding="utf-8"
            )
            files_created["sources.txt"] = len(source_lines)

            logger.info("Exported project structure for %s to %s", domain, recon_dir)

            return ProjectSummary(
                target=domain,
                project_dir=project_dir,
                recon_dir=recon_dir,
                files_created=files_created,
            )

        return await self._with_storage(_export)
