"""Configuration manager to load environment variables, scope, and API keys."""
import json
import logging
from pathlib import Path

import yaml
from dotenv import dotenv_values

from core.processor import normalize_and_validate_domain

logger = logging.getLogger(__name__)


class ConfigManager:
    """Loads and validates scan scopes, out-of-scope targets, plugin filters, and API keys."""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)

        self.api_keys: dict[str, str] = {}
        self.scope: list[str] = []
        self.out_of_scope: list[str] = []
        self.sources: list[str] | None = None
        self.tools: dict[str, dict] = {}

        self._load_env()
        self._load_config_file()

    def _load_env(self) -> None:
        env_path = Path.home() / ".config" / "subx" / ".env"
        if not env_path.exists():
            return
        for key, value in dotenv_values(env_path).items():
            if value:
                self.api_keys[key.upper()] = value

    def _load_config_file(self) -> None:
        if not self.config_path.exists():
            logger.error("File not found: %s", self.config_path)
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                if self.config_path.suffix in {".yaml", ".yml"}:
                    data = yaml.safe_load(f) or {}
                elif self.config_path.suffix == ".json":
                    data = json.load(f) or {}
                else:
                    raise ValueError(
                        f"Unsupported config format '{self.config_path.suffix}'. Use YAML or JSON."
                    )
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            logger.error("Failed to parse config file: %s", e)
            raise

        scope_raw = self._parse_list(data, "scope")
        self.scope = []
        for s in scope_raw:
            try:
                self.scope.append(normalize_and_validate_domain(s))
            except ValueError as e:
                raise ValueError(f"Invalid entry in scope: {e}") from e

        oos_raw = self._parse_list(data, "out_of_scope")
        self.out_of_scope = []
        for s in oos_raw:
            try:
                self.out_of_scope.append(normalize_and_validate_domain(s))
            except ValueError as e:
                raise ValueError(f"Invalid entry in out_of_scope: {e}") from e

        self.sources = self._parse_list(data, "sources") or None

        if not self.scope:
            raise ValueError(
                "Config file must define at least one entry under 'scope'."
            )

        for key, val in data.get("api_keys", {}).items():
            if val:
                self.api_keys[key.upper()] = str(val)

        db_cfg = data.get("db", {})
        if isinstance(db_cfg, dict) and db_cfg:
            import os
            if "host" in db_cfg:
                os.environ["SUBX_DB_HOST"] = str(db_cfg["host"])
            if "user" in db_cfg or "username" in db_cfg:
                os.environ["SUBX_DB_USER"] = str(db_cfg.get("user") or db_cfg.get("username"))
            if "password" in db_cfg or "pass" in db_cfg:
                os.environ["SUBX_DB_PASS"] = str(db_cfg.get("password") or db_cfg.get("pass"))
            if "port" in db_cfg:
                os.environ["SUBX_DB_PORT"] = str(db_cfg["port"])
            if "dbname" in db_cfg or "database" in db_cfg:
                os.environ["SUBX_DB_NAME"] = str(db_cfg.get("dbname") or db_cfg.get("database"))

        # ── Tool parameters ─────────────────────────────────────
        tools_raw = data.get("tools", {})
        if isinstance(tools_raw, dict):
            for tool_name, tool_cfg in tools_raw.items():
                if isinstance(tool_cfg, dict):
                    self.tools[str(tool_name)] = {
                        str(k): v for k, v in tool_cfg.items()
                    }
                elif isinstance(tool_cfg, list):
                    # Support list-of-mappings format: - key: value
                    merged: dict = {}
                    for item in tool_cfg:
                        if isinstance(item, dict):
                            merged.update({str(k): v for k, v in item.items()})
                        elif isinstance(item, str) and ":" in item:
                            k, _, v = item.partition(":")
                            merged[k.strip()] = v.strip()
                    self.tools[str(tool_name)] = merged

    @staticmethod
    def _parse_list(data: dict, key: str) -> list[str]:
        value = data.get(key, [])
        if isinstance(value, list):
            return [str(v).strip() for v in value if v]
        if isinstance(value, str) and value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return []

    def get_api_keys(self) -> dict[str, str]:
        """Get the loaded API credentials."""
        return self.api_keys

    def get_scope(self) -> list[str]:
        """Get the target domains defined in the active scope."""
        return self.scope

    def get_primary(self) -> str:
        """Get the primary target domain (first item in active scope)."""
        return self.scope[0]

    def get_out_of_scope(self) -> list[str]:
        """Get the blacklisted domains defined as out-of-scope."""
        return self.out_of_scope

    def get_sources(self) -> list[str] | None:
        """Get the allowed plugin sources list filter."""
        return self.sources

    def get_tool_config(self, tool_name: str) -> dict:
        """Get CLI parameters for a specific tool (e.g. 'httpx').

        Returns a dict of key-value pairs that map to ``-key value`` flags.
        Returns an empty dict if no config exists for the tool.
        """
        return self.tools.get(tool_name, {})

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a tool is enabled for execution in the tools section."""
        if tool_name not in self.tools:
            return False
        cfg = self.tools[tool_name]
        if isinstance(cfg, dict) and cfg.get("enabled") is False:
            return False
        return True

    def get_all_tool_configs(self) -> dict[str, dict]:
        """Get all tool configurations."""
        return self.tools

    @staticmethod
    def load_tool_config(tool_name: str) -> dict | None:
        """Auto-discover config file and return tool parameters.

        Searches (in order):
          1. ``config.yaml`` / ``config.yml`` / ``config.json`` in CWD
          2. ``~/.config/subx/config.yaml``

        Returns the tool's config dict, or ``None`` if no config found.
        This is a convenience method so commands like ``http-probe`` and
        ``db`` can pick up tool params without requiring ``-c``.
        """
        candidates = [
            Path("config.yaml"),
            Path("config.yml"),
            Path("config.json"),
            Path.home() / ".config" / "subx" / "config.yaml",
        ]
        for candidate in candidates:
            if candidate.is_file():
                try:
                    cfg = ConfigManager(str(candidate))
                    tool_cfg = cfg.get_tool_config(tool_name)
                    return tool_cfg if tool_cfg else None
                except Exception:
                    continue
        return None
