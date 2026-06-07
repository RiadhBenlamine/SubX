import json
import logging
from pathlib import Path
from typing import Optional

import yaml
from dotenv import dotenv_values

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Single source of truth for SubX configuration.

    Load order (last wins):
        1. ~/.config/subx/.env   — global API keys
        2. config file (-c)      — target, scope, oos, sources, api_keys

    Supported config formats: YAML (.yaml / .yml), JSON (.json)
    """

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)

        self.target: str = ""
        self.api_keys: dict[str, str] = {}
        self.scope: list[str] = []
        self.out_of_scope: list[str] = []
        self.sources: Optional[list[str]] = None

        self._load_env()
        self._load_config_file()

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    def _load_env(self) -> None:
        """Load API keys from ~/.config/subx/.env (global, set once)."""
        env_path = Path.home() / ".config" / "subx" / ".env"
        if not env_path.exists():
            return
        for key, value in dotenv_values(env_path).items():
            if value:
                self.api_keys[key.upper()] = value

    def _load_config_file(self) -> None:
        """Parse the config file and populate all fields."""
        if not self.config_path.exists():
            logger.error("[Config] File not found: %s", self.config_path)
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
            logger.error("[Config] Failed to parse config file: %s", e)
            raise

        self.target      = self._parse_str(data, "target")
        self.scope       = self._parse_list(data, "scope")
        self.out_of_scope = self._parse_list(data, "out_of_scope")
        self.sources     = self._parse_list(data, "sources") or None

        # api_keys in config override .env
        for key, val in data.get("api_keys", {}).items():
            if val:
                self.api_keys[key.upper()] = str(val)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_str(data: dict, key: str) -> str:
        value = data.get(key, "")
        return str(value).strip() if value else ""

    @staticmethod
    def _parse_list(data: dict, key: str) -> list[str]:
        value = data.get(key, [])
        if isinstance(value, list):
            return [str(v).strip() for v in value if v]
        if isinstance(value, str) and value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return []

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_target(self) -> str:
        return self.target

    def get_api_keys(self) -> dict[str, str]:
        return self.api_keys

    def get_scope(self) -> list[str]:
        """Return configured scope, falling back to [target]."""
        return self.scope if self.scope else [self.target]

    def get_out_of_scope(self) -> list[str]:
        return self.out_of_scope

    def get_sources(self) -> Optional[list[str]]:
        """Return plugin whitelist, or None meaning run all."""
        return self.sources