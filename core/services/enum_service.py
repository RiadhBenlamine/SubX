"""Service layer orchestrating domain subdomain passive enumeration."""
import asyncio
from dataclasses import dataclass, field

from core.config_manager import ConfigManager
from core.models import ProcessedResult
from core.plugin_manager import PluginManager
from core.processor import Processor
from core.services.base import Service


@dataclass
class EnumResult:
    """Structured output from a full enumeration run."""
    scope: list[str]
    out_of_scope: list[str]
    sources: list[str] | None
    plugin_names: list[str]
    processed_by_target: dict[str, dict] = field(default_factory=dict)
    probe_results_by_target: dict[str, tuple[list[dict], list]] = field(default_factory=dict)


class EnumService(Service):
    """Orchestrates subdomain enumeration: config → plugins → process → store → tool pipeline."""

    async def run(
        self,
        config_path: str,
        save: bool,
        progress_cb=None,
        status_cb=None,
    ) -> EnumResult:
        """Parse configuration, launch discovery plugins, collect and persist results."""
        config = self._load_config(config_path)
        scope = config.get_scope()

        pm = PluginManager(config.get_api_keys())
        pm.load_plugins(allowed=config.get_sources())

        if not pm.loaded_plugins:
            raise RuntimeError("No plugins loaded. Check your API keys or sources in config.")

        result = EnumResult(
            scope=scope,
            out_of_scope=config.get_out_of_scope(),
            sources=config.get_sources(),
            plugin_names=[p.__class__.__name__ for p in pm.loaded_plugins],
        )

        processor = Processor(scope=scope, out_of_scope=config.get_out_of_scope())

        storage = None
        if save:
            storage = self.storage
            await storage.init()

        try:
            # Run domains sequentially so circuit-breaker state propagates:
            # if a plugin trips on domain 1, it is skipped for domains 2–N.
            domain_results = []
            for domain in scope:
                dr = await self._run_domain(pm, processor, domain, progress_cb=progress_cb, status_cb=status_cb)
                domain_results.append(dr)

            for domain, processed in zip(scope, domain_results):
                new_count = 0
                if storage:
                    new_count = await storage.save(processed, target=domain)
                    if config.is_tool_enabled("httpx"):
                        rows = await storage.get_all(domain)
                        result.probe_results_by_target[domain] = ([], rows)
                result.processed_by_target[domain] = {
                    "processed": processed,
                    "new_count": new_count,
                }
        finally:
            pass  # Don't dispose — singleton is reused

        return result

    async def _run_domain(
        self,
        pm: PluginManager,
        processor: Processor,
        domain: str,
        progress_cb=None,
        status_cb=None,
    ) -> ProcessedResult:
        raw = await pm.execute_plugins(domain, progress_cb=progress_cb, status_cb=status_cb)
        processed = processor.process(raw)

        if not processor.has_wildcards(processed):
            return processed

        wc_domains = [
            d for d in processor.extract_wildcard_domains(processed)
            if d.lower() != domain.lower()
        ][:5]

        if not wc_domains:
            return processed

        if status_cb:
            status_cb(f"Processing {len(wc_domains)} wildcard domain(s)...")

        async def _run_wc(wc: str):
            try:
                return await asyncio.wait_for(pm.execute_plugins(wc), timeout=30.0)
            except Exception:
                return []

        wc_batches = await asyncio.gather(*(_run_wc(wc) for wc in wc_domains))

        for wc_raw in wc_batches:
            if wc_raw:
                processed = processor.merge(processed, processor.process(wc_raw))

        return processed

    @staticmethod
    def _load_config(config_path: str) -> ConfigManager:
        return ConfigManager(config_path=config_path)
