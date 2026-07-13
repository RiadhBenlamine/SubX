"""Data models for plugin execution and parsed subdomain reconciliation results."""
from dataclasses import dataclass, field
from datetime import datetime

from core.db_models import _utc_now


@dataclass
class PluginResult:
    """Outcome of a single plugin run, including errors and metadata."""

    plugin_name: str
    subdomains: list[str] = field(default_factory=list)
    error: Exception | None = None
    status: str = "ok"
    finished_at: datetime = field(default_factory=_utc_now)

    @property
    def success(self) -> bool:
        """Return True if the plugin executed without raising errors."""
        return self.error is None


@dataclass
class ProcessedResult:
    """Consolidated, validated scan scope findings categorized by scopes."""

    by_plugin: dict[str, list[str]] = field(default_factory=dict)
    wildcards: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    plugin_statuses: dict[str, str] = field(default_factory=dict)
    finished_at: datetime = field(default_factory=_utc_now)
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def _invalidate(self) -> None:
        """Flush the internal cached property computations."""
        self._cache.clear()

    @property
    def all_subdomains(self) -> list[str]:
        """Compute the flat, sorted list of all unique discovered subdomains."""
        if "all" not in self._cache:
            seen: set[str] = set()
            result: list[str] = []
            for subs in self.by_plugin.values():
                for sub in subs:
                    if sub not in seen:
                        seen.add(sub)
                        result.append(sub)
            self._cache["all"] = sorted(result)
        return self._cache["all"]

    @property
    def total(self) -> int:
        """Count the absolute number of unique subdomains across all sources."""
        if "total" in self._cache:
            return self._cache["total"]
        seen: set[str] = set()
        for subs in self.by_plugin.values():
            seen.update(subs)
        self._cache["total"] = len(seen)
        return self._cache["total"]
