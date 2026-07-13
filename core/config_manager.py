"""Configuration manager to load environment variables, scope, and API keys."""
import json
import logging
from pathlib import Path
from typing import Optional

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
        self.sources: Optional[list[str]] = None

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

    def get_sources(self) -> Optional[list[str]]:
        """Get the allowed plugin sources list filter."""
        return self.sources
