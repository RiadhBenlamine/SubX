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
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def _invalidate(self) -> None:
        self._cache.clear()

    @property
    def all_subdomains(self) -> list[str]:
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
        if "total" in self._cache:
            return self._cache["total"]
        seen: set[str] = set()
        for subs in self.by_plugin.values():
            seen.update(subs)
        self._cache["total"] = len(seen)
        return self._cache["total"]