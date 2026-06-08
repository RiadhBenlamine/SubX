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

    Plugins with an empty required_keys() are always loaded (no API key needed).
    Plugins with required_keys() that are missing from config are skipped with a warning.
    """

    def __init__(self, config: dict):
        self.config         = config
        self.plugins_path   = pathlib.Path(__file__).parent.parent / "plugins"
        self.loaded_plugins: list[Plugin] = []
        self._lock          = Lock()

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def load_plugins(self, allowed: list[str] | None = None) -> None:
        """
        Discover and load all valid Plugin subclasses from the plugins directory.
        Thread-safe. No-op if plugins are already loaded.

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
                    name = plugin.__class__.__name__

                    # Whitelist filter
                    if allowed is not None and name not in allowed:
                        logger.debug("[PluginManager] Skipping %s — not in allowed sources.", name)
                        continue

                    # Key check — plugins with no required keys always pass
                    missing = self._missing_keys(plugin)
                    if missing:
                        logger.warning(
                            "[PluginManager] Skipping %s — missing config key(s): %s",
                            name, missing,
                        )
                        continue

                    self.loaded_plugins.append(plugin)
                    logger.debug("[PluginManager] Loaded %s.", name)

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

    # ──────────────────────────────────────────────────────────────
    # Discovery
    # ──────────────────────────────────────────────────────────────

    def _discover_modules(self) -> list[pathlib.Path]:
        """
        Glob the plugins directory for valid .py files.
        Excludes __init__.py and any private _*.py files.
        """
        return [
            path for path in self.plugins_path.glob("*.py")
            if not path.name.startswith("_")
        ]

    # ──────────────────────────────────────────────────────────────
    # Import
    # ──────────────────────────────────────────────────────────────

    def _import_module(self, path: pathlib.Path):
        """Dynamically import a module by path. Returns None on failure."""
        module_name = f"plugins.{path.stem}"
        try:
            return importlib.import_module(module_name)
        except Exception as e:
            logger.warning("[PluginManager] Failed to import '%s': %s", module_name, e)
            return None

    # ──────────────────────────────────────────────────────────────
    # Extraction
    # ──────────────────────────────────────────────────────────────

    def _extract_plugins(self, module) -> list[Plugin]:
        """
        Inspect a module and return instantiated Plugin subclasses
        defined in that module (not merely imported into it).
        """
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
        """Check that a class is a concrete Plugin subclass defined in this module."""
        return (
            issubclass(cls, Plugin)
            and cls is not Plugin
            and cls.__module__ == module.__name__
        )

    def _instantiate(self, cls) -> Plugin | None:
        """Instantiate a plugin with the current config. Returns None on failure."""
        try:
            return cls(self.config)
        except Exception as e:
            logger.warning("[PluginManager] Failed to instantiate '%s': %s", cls.__name__, e)
            return None

    # ──────────────────────────────────────────────────────────────
    # Configuration validation
    # ──────────────────────────────────────────────────────────────

    def _missing_keys(self, plugin: Plugin) -> list[str]:
        """
        Return a list of required keys that are absent or empty in config.
        Returns [] for plugins that need no API keys — they always load.

        Handles both property and method style required_keys definitions.
        """
        try:
            keys = plugin.required_keys
            # If defined as a method rather than a property, call it
            if callable(keys):
                keys = keys()
        except Exception as e:
            logger.warning(
                "[PluginManager] Could not read required_keys from %s: %s",
                plugin.__class__.__name__, e,
            )
            return []

        return [k for k in keys if self.config.get(k) in (None, "")]