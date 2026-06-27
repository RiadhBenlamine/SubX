import logging

from core.models import PluginResult, ProcessedResult

logger = logging.getLogger(__name__)


class Processor:
    WILDCARD_PREFIX = "*."

    def __init__(self, scope: list[str], out_of_scope: list[str] | None = None):
        if not scope:
            raise ValueError("Processor requires at least one entry in scope.")

        self.scope = scope
        self.out_of_scope = out_of_scope or []

        self._scope_suffixes: tuple[str, ...] = tuple(f".{s}" for s in self.scope)
        self._scope_exact: frozenset[str] = frozenset(self.scope)
        self._oos_suffixes: tuple[str, ...] = tuple(f".{s}" for s in self.out_of_scope)
        self._oos_exact: frozenset[str] = frozenset(self.out_of_scope)

    def process(self, results: list[PluginResult]) -> ProcessedResult:
        by_plugin: dict[str, list[str]] = {}
        all_wildcards: set[str] = set()
        all_oos: set[str] = set()

        for result in results:
            if not result.success:
                logger.warning("Skipping failed plugin: %s", result.plugin_name)
                continue

            clean, wildcards, oos = self._classify(result.subdomains)
            all_wildcards.update(wildcards)
            all_oos.update(oos)

            if clean:
                by_plugin[result.plugin_name] = sorted(clean)

        return ProcessedResult(
            by_plugin=by_plugin,
            wildcards=sorted(w[2:] for w in all_wildcards),
            out_of_scope=list(all_oos),
        )

    def merge(self, base: ProcessedResult, incoming: ProcessedResult) -> ProcessedResult:
        for plugin_name, subs in incoming.by_plugin.items():
            if plugin_name in base.by_plugin:
                merged = set(base.by_plugin[plugin_name])
                merged.update(subs)
                base.by_plugin[plugin_name] = sorted(merged)
            else:
                base.by_plugin[plugin_name] = sorted(subs)

        base.wildcards = sorted(set(base.wildcards) | set(incoming.wildcards))
        base.out_of_scope = list(set(base.out_of_scope) | set(incoming.out_of_scope))
        base._invalidate()
        return base

    def has_wildcards(self, result: ProcessedResult) -> bool:
        return bool(result.wildcards)

    def extract_wildcard_domains(self, result: ProcessedResult) -> list[str]:
        return result.wildcards

    def _classify(self, subdomains: list[str]) -> tuple[set[str], set[str], set[str]]:
        clean: set[str] = set()
        wildcards: set[str] = set()
        out_of_scope: set[str] = set()

        for sub in subdomains:
            sub = sub.strip().lower()
            if not sub:
                continue
            if sub.startswith(self.WILDCARD_PREFIX):
                wildcards.add(sub)
            elif not self._in_scope(sub):
                out_of_scope.add(sub)
            else:
                clean.add(sub)

        return clean, wildcards, out_of_scope

    def _in_scope(self, subdomain: str) -> bool:
        if subdomain in self._oos_exact or subdomain.endswith(self._oos_suffixes):
            return False
        return subdomain in self._scope_exact or subdomain.endswith(self._scope_suffixes)