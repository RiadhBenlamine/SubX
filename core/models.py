from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class PluginResult:
    plugin_name: str
    subdomains: list[str] = field(default_factory=list)
    error: Exception | None = None
    finished_at: datetime = field(default_factory=_utc_now)

    @property
    def count(self) -> int:
        return len(self.subdomains)

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class ProcessedResult:
    by_plugin: dict[str, list[str]] = field(default_factory=dict)
    wildcards: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    finished_at: datetime = field(default_factory=_utc_now)

    @property
    def all_subdomains(self) -> list[str]:
        """Flat deduplicated sorted list across all plugins."""
        seen = set()
        result = []
        for subs in self.by_plugin.values():
            for sub in subs:
                if sub not in seen:
                    seen.add(sub)
                    result.append(sub)
        return sorted(result)

    @property
    def total(self) -> int:
        return len(self.all_subdomains)