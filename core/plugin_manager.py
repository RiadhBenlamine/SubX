import asyncio
import importlib
import inspect
import logging
import pathlib

from core.models import PluginResult
from core.plugin import Plugin

logger = logging.getLogger("PluginManager")


class PluginManager:
    def __init__(self, config: dict):
        self.config = config
        self.plugins_path = pathlib.Path(__file__).parent.parent / "plugins"
        self.loaded_plugins: list[Plugin] = []

    def load_plugins(self, allowed: list[str] | None = None) -> None:
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
        if not self.loaded_plugins:
            logger.warning("No plugins loaded. Call load_plugins() first.")
            return []

        plugins = self.loaded_plugins
        names = [p.__class__.__name__ for p in plugins]
        outcomes = await asyncio.gather(
            *(p.run(target) for p in plugins),
            return_exceptions=True,
        )

        results: list[PluginResult] = []
        for name, outcome in zip(names, outcomes):
            if isinstance(outcome, Exception):
                logger.error("[%s] failed: %s", name, outcome)
                results.append(PluginResult(plugin_name=name, error=outcome))
            else:
                results.append(PluginResult(
                    plugin_name=name,
                    subdomains=outcome if isinstance(outcome, list) else [],
                ))
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
        except Exception as e:
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
    def _is_valid_plugin(cls, module) -> bool:
        return (
            issubclass(cls, Plugin)
            and cls is not Plugin
            and cls.__module__ == module.__name__
        )

    def _instantiate(self, cls) -> Plugin | None:
        try:
            return cls(self.config)
        except Exception as e:
            logger.warning("Failed to instantiate '%s': %s", cls.__name__, e)
            return None

    def _missing_keys(self, plugin: Plugin) -> list[str]:
        try:
            keys = plugin.required_keys
            if callable(keys):
                keys = keys()
        except Exception as e:
            logger.warning("Could not read required_keys from %s: %s", plugin.__class__.__name__, e)
            return []
        return [k for k in keys if self.config.get(k) in (None, "")]