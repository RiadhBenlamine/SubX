import asyncio
import importlib
import inspect
import logging
import pathlib
from threading import Lock

from core.plugin import Plugin
from core.models import PluginResult

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Discovers, loads, and executes plugins from the plugins directory.

    Lifecycle:
        1. load_plugins()    — discover and instantiate all valid plugins
        2. execute_plugins() — run all loaded plugins concurrently against a target
    """

    def __init__(self, config: dict):
        self.config = config
        self.plugins_path = pathlib.Path(__file__).parent.parent / "plugins"
        self.loaded_plugins: list[Plugin] = []
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_plugins(self, allowed: list[str] | None = None) -> None:
        """
        Discover and load all valid Plugin subclasses from the plugins directory.
        Thread-safe. Skips already-loaded state, unconfigured plugins, and bad imports.

        Args:
            allowed: optional whitelist of plugin class names.
                     If None, all configured plugins are loaded.
        """
        with self._lock:
            if self.loaded_plugins:
                logger.debug("[PluginManager] Plugins already loaded, skipping.")
                return

            for module_path in self._discover_modules():
                module = self._import_module(module_path)
                if module is None:
                    continue

                for plugin in self._extract_plugins(module):
                    if allowed is not None and plugin.__class__.__name__ not in allowed:
                        logger.debug(
                            "[PluginManager] Skipping %s — not in allowed sources.",
                            plugin.__class__.__name__,
                        )
                        continue

                    if self._is_configured(plugin):
                        self.loaded_plugins.append(plugin)
                    else:
                        self._warn_missing_keys(plugin)

            logger.info(
                "[PluginManager] Loaded %d plugin(s): %s",
                len(self.loaded_plugins),
                [p.__class__.__name__ for p in self.loaded_plugins],
            )

    async def execute_plugins(self, target: str) -> list[PluginResult]:
        """
        Run all loaded plugins concurrently against the given target.

        Returns:
            list of PluginResult — raw, unfiltered, unordered.
        """
        if not self.loaded_plugins:
            logger.warning("[PluginManager] No plugins loaded. Call load_plugins() first.")
            return []

        names, coroutines = zip(*[
            (plugin.__class__.__name__, plugin.run(target))
            for plugin in self.loaded_plugins
        ])

        outcomes = await asyncio.gather(*coroutines, return_exceptions=True)

        results = []
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

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover_modules(self) -> list[pathlib.Path]:
        """
        Glob the plugins directory for valid .py files.
        Excludes __init__.py and any private _*.py files.
        """
        return [
            path for path in self.plugins_path.glob("*.py")
            if not path.name.startswith("_")
        ]

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _import_module(self, path: pathlib.Path):
        """
        Dynamically import a module by path.
        Returns the module on success, None on failure.
        """
        module_name = f"plugins.{path.stem}"
        try:
            return importlib.import_module(module_name)
        except Exception as e:
            logger.warning("[PluginManager] Failed to import '%s': %s", module_name, e)
            return None

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract_plugins(self, module) -> list[Plugin]:
        """
        Inspect a module and return instantiated Plugin subclasses
        defined in that module (not merely imported into it).
        """
        plugins = []

        for name, cls in inspect.getmembers(module, inspect.isclass):
            if not self._is_valid_plugin(cls, module):
                continue
            instance = self._instantiate(name, cls)
            if instance is not None:
                plugins.append(instance)

        return plugins

    @staticmethod
    def _is_valid_plugin(cls, module) -> bool:
        """Check that a class is a concrete Plugin subclass defined in this module."""
        return (
            issubclass(cls, Plugin)
            and cls is not Plugin
            and cls.__module__ == module.__name__
        )

    def _instantiate(self, name: str, cls) -> Plugin | None:
        """Instantiate a plugin with the current config. Returns None on failure."""
        try:
            return cls(self.config)
        except Exception as e:
            logger.warning("[PluginManager] Failed to instantiate '%s': %s", name, e)
            return None

    # ------------------------------------------------------------------
    # Configuration validation
    # ------------------------------------------------------------------

    def _is_configured(self, plugin: Plugin) -> bool:
        """
        Check that all required API keys declared by the plugin
        are present and non-empty in the config.
        Plugins with no required_keys always pass.
        """
        return all(
            self.config.get(key) not in (None, "")
            for key in plugin.required_keys
        )

    def _warn_missing_keys(self, plugin: Plugin) -> None:
        """Log a warning listing which required keys are missing for a plugin."""
        missing = [
            key for key in plugin.required_keys
            if not self.config.get(key)
        ]
        logger.warning(
            "[PluginManager] Skipping %s — missing config keys: %s",
            plugin.__class__.__name__,
            missing,
        )