"""Plugin manager for discovering, loading, and executing subdomain discovery plugins."""
import asyncio
import importlib
import inspect
import logging
import pathlib

from core.errors import PluginAuthError, PluginRateLimitError, PluginUnavailableError
from core.models import PluginResult
from core.plugin import Plugin

logger = logging.getLogger("PluginManager")


class PluginManager:
    """Manages the discovery, initialization, and concurrent execution of passive recon plugins."""

    def __init__(self, config: dict):
        self.config = config
        self.plugins_path = pathlib.Path(__file__).parent.parent / "plugins"
        self.loaded_plugins: list[Plugin] = []

    def load_plugins(self, allowed: list[str] | None = None) -> None:
        """Scan the plugins directory and load configured/authorized plugin classes."""
        if self.loaded_plugins:
            return

        for module_path in self._discover_modules():
            module = self._import_module(module_path)
            if module is None:
                continue

            for plugin in self._extract_plugins(module):
                name = plugin.__class__.__name__

                if allowed is not None and name not in allowed:
                    logger.debug("Skipping %s — not in allowed sources.", name)
                    continue

                missing = self._missing_keys(plugin)
                if missing:
                    logger.warning("Skipping %s — missing config key(s): %s", name, missing)
                    continue

                self.loaded_plugins.append(plugin)
                logger.debug("Loaded %s.", name)

        logger.info(
            "Loaded %d plugin(s): %s",
            len(self.loaded_plugins),
            [p.__class__.__name__ for p in self.loaded_plugins],
        )

    async def execute_plugins(self, target: str) -> list[PluginResult]:
        """Execute all loaded plugins concurrently against a target domain.

        Plugins whose circuit breaker has been tripped are skipped entirely —
        no network call is made. After execution, any rate-limit or auth
        failure will trip the offending plugin's circuit so it is skipped for
        all subsequent domains.
        """
        if not self.loaded_plugins:
            logger.warning("No plugins loaded. Call load_plugins() first.")
            return []

        results: list[PluginResult] = []

        # Separate active plugins from already-tripped ones
        active: list[Plugin] = []
        for plugin in self.loaded_plugins:
            name = plugin.__class__.__name__
            if plugin.tripped:
                logger.debug("[%s] skipped — circuit already tripped.", name)
                results.append(
                    PluginResult(
                        plugin_name=name,
                        subdomains=[],
                        error=PluginRateLimitError(
                            f"{name} skipped — circuit tripped."
                        ),
                        status="rate_limited",
                    )
                )
            else:
                active.append(plugin)

        if not active:
            return results

        async def _run_with_timeout(p: Plugin, tgt: str):
            try:
                return await asyncio.wait_for(p.run(tgt), timeout=30.0)
            except asyncio.TimeoutError:
                raise PluginUnavailableError("Plugin query timed out after 30s.")

        # Run only active plugins concurrently
        outcomes = await asyncio.gather(
            *(_run_with_timeout(p, target) for p in active),
            return_exceptions=True,
        )

        for plugin, outcome in zip(active, outcomes):
            name = plugin.__class__.__name__
            if isinstance(outcome, Exception):
                logger.error("[%s] failed: %s", name, outcome)
                status = "unavailable"
                subdomains: list[str] = []

                if isinstance(outcome, PluginAuthError):
                    status = "auth_error"
                    plugin.trip_circuit(str(outcome))
                elif isinstance(outcome, PluginRateLimitError):
                    status = "rate_limited"
                    subdomains = getattr(outcome, "partial_subdomains", [])
                    plugin.trip_circuit(str(outcome))
                elif isinstance(outcome, PluginUnavailableError):
                    status = "unavailable"

                results.append(
                    PluginResult(
                        plugin_name=name,
                        subdomains=subdomains,
                        error=outcome,
                        status=status,
                    )
                )
            else:
                results.append(
                    PluginResult(
                        plugin_name=name,
                        subdomains=outcome if isinstance(outcome, list) else [],
                        status="ok",
                    )
                )
        return results

    def _discover_modules(self) -> list[pathlib.Path]:
        return [
            path for path in self.plugins_path.glob("*.py")
            if not path.name.startswith("_")
        ]

    def _import_module(self, path: pathlib.Path):
        module_name = f"plugins.{path.stem}"
        try:
            return importlib.import_module(module_name)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to import '%s': %s", module_name, e)
            return None

    def _extract_plugins(self, module) -> list[Plugin]:
        plugins = []
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not self._is_valid_plugin(cls, module):
                continue
            instance = self._instantiate(cls)
            if instance is not None:
                plugins.append(instance)
        return plugins

    @staticmethod
    def _is_valid_plugin(plugin_cls, module) -> bool:
        return (
            issubclass(plugin_cls, Plugin)
            and plugin_cls is not Plugin
            and plugin_cls.__module__ == module.__name__
        )

    def _instantiate(self, cls) -> Plugin | None:
        try:
            return cls(self.config)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to instantiate '%s': %s", cls.__name__, e)
            return None

    def _missing_keys(self, plugin: Plugin) -> list[str]:
        try:
            keys = plugin.required_keys
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Could not read required_keys from %s: %s", plugin.__class__.__name__, e)
            return []
        return [k for k in keys if self.config.get(k) in (None, "")]
