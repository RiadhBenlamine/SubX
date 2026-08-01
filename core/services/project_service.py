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

            # Sets of alive and dead subdomains for reciprocal cleanup
            alive_subs_set = {r.subdomain for r in rows if r.alive is True}
            dead_subs_set = {r.subdomain for r in rows if r.alive is False}

            # 1. subdomains.txt — all subdomains
            all_subs = [r.subdomain for r in rows]
            files_created["subdomains.txt"] = self._save_deduped(
                recon_dir / "subdomains.txt", all_subs
            )

            # 2. alive.txt — subdomains verified alive
            alive_subs = [r.subdomain for r in rows if r.alive is True]
            files_created["alive.txt"] = self._save_deduped(
                recon_dir / "alive.txt", alive_subs, remove_lines=dead_subs_set
            )

            # 3. dead.txt — subdomains currently down
            dead_subs = [r.subdomain for r in rows if r.alive is False]
            files_created["dead.txt"] = self._save_deduped(
                recon_dir / "dead.txt", dead_subs, remove_lines=alive_subs_set
            )

            # 4. techs.txt — subdomains with detected technologies
            tech_lines = [
                f"{r.subdomain} [{_format_tech(r.tech)}]" for r in rows if r.tech
            ]
            files_created["techs.txt"] = self._save_deduped(
                recon_dir / "techs.txt", tech_lines
            )

            # 5. status.txt — HTTP status code and title for probed subdomains
            status_lines = [
                f"{r.subdomain} [{r.status_code or '—'}] [{r.title or '—'}]"
                for r in rows
                if r.status_code is not None or r.title
            ]
            files_created["status.txt"] = self._save_deduped(
                recon_dir / "status.txt", status_lines
            )

            # 6. ips.txt — subdomains with IP addresses
            ip_lines = [f"{r.subdomain} [{r.ip}]" for r in rows if r.ip]
            files_created["ips.txt"] = self._save_deduped(
                recon_dir / "ips.txt", ip_lines
            )

            # 7. sources.txt — subdomains with discovery sources
            source_lines = []
            for r in rows:
                sources_str = (
                    ", ".join(s.source_plugin for s in r.sources)
                    if getattr(r, "sources", None)
                    else r.source_plugin
                )
                source_lines.append(f"{r.subdomain} [{sources_str}]")
            files_created["sources.txt"] = self._save_deduped(
                recon_dir / "sources.txt", source_lines
            )

            logger.info("Exported project structure for %s to %s", domain, recon_dir)

            return ProjectSummary(
                target=domain,
                project_dir=project_dir,
                recon_dir=recon_dir,
                files_created=files_created,
            )

        return await self._with_storage(_export)

    @staticmethod
    def _save_deduped(
        file_path: Path,
        new_lines: list[str],
        remove_lines: set[str] | None = None,
    ) -> int:
        """Read existing file if present, filter out remove_lines, merge new_lines without duplicates, write back."""
        existing_lines: list[str] = []
        seen: set[str] = set()

        remove_set = remove_lines or set()

        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped and stripped not in remove_set and stripped not in seen:
                        seen.add(stripped)
                        existing_lines.append(stripped)
            except Exception:
                pass

        merged = list(existing_lines)
        for line in new_lines:
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                merged.append(stripped)

        file_path.write_text(
            "\n".join(merged) + ("\n" if merged else ""), encoding="utf-8"
        )
        return len(merged)
