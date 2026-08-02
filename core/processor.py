"""Processor for validating, filtering, and classifying discovered subdomains."""
import logging
import re

from core.models import PluginResult, ProcessedResult

logger = logging.getLogger(__name__)

HOSTNAME_REGEX = re.compile(r"^[a-zA-Z0-9.-]+$")


def normalize_and_validate_domain(domain_str: str) -> str:
    """Normalize domain to lowercase, strip trailing dots/spaces, and validate format."""
    d = domain_str.strip().lower()
    while d.endswith("."):
        d = d[:-1]
    if not d:
        raise ValueError("Domain entry cannot be empty.")
    if not HOSTNAME_REGEX.match(d):
        raise ValueError(
            f"Domain '{domain_str}' contains invalid characters. "
            "Must contain only alphanumeric characters, dots, and hyphens."
        )
    if ".." in d or d.startswith(".") or d.startswith("-") or d.endswith("-"):
        raise ValueError(f"Domain '{domain_str}' is malformed.")
    return d


def matches_boundary(sub: str, parent: str) -> bool:
    """Check if subdomain matches target domain on label boundaries."""
    return sub == parent or sub.endswith("." + parent)


class Processor:
    """Classifies subdomain scan findings into wildcards, in-scope, and out-of-scope targets."""

    WILDCARD_PREFIX = "*."

    def __init__(self, scope: list[str], out_of_scope: list[str] | None = None):
        if not scope:
            raise ValueError("Processor requires at least one entry in scope.")

        self.scope = [normalize_and_validate_domain(s) for s in scope]
        self.out_of_scope = [
            normalize_and_validate_domain(s) for s in (out_of_scope or [])
        ]

    def process(self, results: list[PluginResult]) -> ProcessedResult:
        """Classify subdomains from plugin execution outcomes into scope categories."""
        by_plugin: dict[str, list[str]] = {}
        all_wildcards: set[str] = set()
        all_oos: set[str] = set()
        plugin_statuses: dict[str, str] = {}

        for result in results:
            plugin_statuses[result.plugin_name] = result.status
            if not result.subdomains and not result.success:
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
            plugin_statuses=plugin_statuses,
        )

    def merge(self, base: ProcessedResult, incoming: ProcessedResult) -> ProcessedResult:
        """Merge a new scan result into an existing result structure."""
        for plugin_name, subs in incoming.by_plugin.items():
            if plugin_name in base.by_plugin:
                merged = set(base.by_plugin[plugin_name])
                merged.update(subs)
                base.by_plugin[plugin_name] = sorted(merged)
            else:
                base.by_plugin[plugin_name] = sorted(subs)

        for name, status in incoming.plugin_statuses.items():
            if name not in base.plugin_statuses or base.plugin_statuses[name] == "ok":
                base.plugin_statuses[name] = status

        base.wildcards = sorted(set(base.wildcards) | set(incoming.wildcards))
        base.out_of_scope = list(set(base.out_of_scope) | set(incoming.out_of_scope))
        # pylint: disable=protected-access
        base._invalidate()
        return base

    def has_wildcards(self, result: ProcessedResult) -> bool:
        """Return True if the scan results contain wildcards."""
        return bool(result.wildcards)

    def extract_wildcard_domains(self, result: ProcessedResult) -> list[str]:
        """Extract clean wildcard parent domains without the '*.' prefix."""
        clean_domains = []
        for wc in result.wildcards:
            d = wc[2:] if wc.startswith("*.") else wc
            if d and d not in clean_domains:
                clean_domains.append(d)
        return clean_domains

    def _classify(self, subdomains: list[str]) -> tuple[set[str], set[str], set[str]]:
        clean: set[str] = set()
        wildcards: set[str] = set()
        out_of_scope: set[str] = set()

        for sub in subdomains:
            sub = sub.strip().lower()
            while sub.endswith("."):
                sub = sub[:-1]
            if not sub:
                continue

            # Input validation: reject entries with invalid characters
            val_sub = sub[2:] if sub.startswith(self.WILDCARD_PREFIX) else sub
            if (
                not HOSTNAME_REGEX.match(val_sub)
                or ".." in val_sub
                or val_sub.startswith(".")
                or val_sub.startswith("-")
                or val_sub.endswith("-")
            ):
                logger.warning("Dropped invalid subdomain entry: %s", sub)
                continue

            if sub.startswith(self.WILDCARD_PREFIX):
                wildcards.add(sub)
            elif not self._in_scope(sub):
                out_of_scope.add(sub)
            else:
                clean.add(sub)

        return clean, wildcards, out_of_scope

    def _in_scope(self, subdomain: str) -> bool:
        for oos in self.out_of_scope:
            if matches_boundary(subdomain, oos):
                return False
        for sc in self.scope:
            if matches_boundary(subdomain, sc):
                return True
        return False
