import logging
from core.models import PluginResult, ProcessedResult

logger = logging.getLogger(__name__)


class Processor:
    """
    Transforms raw PluginResult list into a clean ProcessedResult.

    Pipeline per plugin:
        1. _classify()            — single pass: bucket into clean/wildcard/oos
                                    all three buckets deduped via dict keys
        2. _finalize_wildcards()  — strip *. prefix, dedup, sort

    Wildcard contract:
        Wildcards are stripped and returned in ProcessedResult.wildcards
        so the caller can re-feed them into PluginManager and call merge()
        to fold results back in.
    """

    WILDCARD_PREFIX = "*."

    def __init__(
        self,
        scope: list[str],
        out_of_scope: list[str] | None = None,
    ):
        """
        Args:
            scope:        required — list of allowed domain suffixes to scan.
                          e.g. ["telekom.de", "t-mobile.com"]
            out_of_scope: blacklisted domain suffixes/exact domains.
        """
        if not scope:
            raise ValueError("Processor requires at least one entry in scope.")

        self.scope = scope
        self.out_of_scope = out_of_scope or []

        # precompute once — avoids recomputing f-strings on every _in_scope call
        self._scope_suffixes: tuple[str, ...] = tuple(f".{s}" for s in self.scope)
        self._scope_exact: frozenset[str] = frozenset(self.scope)

        self._oos_suffixes: tuple[str, ...] = tuple(f".{s}" for s in self.out_of_scope)
        self._oos_exact: frozenset[str] = frozenset(self.out_of_scope)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, results: list[PluginResult]) -> ProcessedResult:
        """
        Process a raw list of PluginResults into a ProcessedResult.

        Args:
            results: raw output from PluginManager.execute_plugins()

        Returns:
            ProcessedResult — wildcards separated, scope filtered,
            deduped and sorted per plugin source.
        """
        by_plugin: dict[str, list[str]] = {}
        all_wildcards: dict[str, None] = {}
        all_oos: dict[str, None] = {}

        for result in results:
            if not result.success:
                logger.warning("[Processor] Skipping failed plugin: %s", result.plugin_name)
                continue

            clean, wildcards, oos = self._classify(result.subdomains)

            all_wildcards.update(wildcards)
            all_oos.update(oos)

            if clean:
                by_plugin[result.plugin_name] = clean

        return self._build_result(
            by_plugin=by_plugin,
            wildcards=self._finalize_wildcards(all_wildcards),
            out_of_scope=list(all_oos),
        )

    def merge(self, base: ProcessedResult, incoming: ProcessedResult) -> ProcessedResult:
        """
        Merge an incoming ProcessedResult into a base ProcessedResult.
        Deduplicates and re-sorts per plugin after merge.
        New plugins from incoming are sorted before insertion.

        Used after wildcard re-scans to fold results back into the main result.
        """
        for plugin_name, subs in incoming.by_plugin.items():
            if plugin_name in base.by_plugin:
                base.by_plugin[plugin_name] = self._dedup_and_sort(
                    base.by_plugin[plugin_name] + subs
                )
            else:
                base.by_plugin[plugin_name] = sorted(subs)

        base.wildcards = sorted(set(base.wildcards) | set(incoming.wildcards))
        base.out_of_scope = list(set(base.out_of_scope) | set(incoming.out_of_scope))

        return base

    def has_wildcards(self, result: ProcessedResult) -> bool:
        """Returns True if wildcards were found during processing."""
        return bool(result.wildcards)

    def extract_wildcard_domains(self, result: ProcessedResult) -> list[str]:
        """
        Returns wildcard domains ready to be re-fed into PluginManager.

        Example:
            *.mail.telekom.de -> mail.telekom.de (already stripped in process())
        """
        return result.wildcards

    # ------------------------------------------------------------------
    # Classification — single pass, all buckets deduped via dict
    # ------------------------------------------------------------------

    def _classify(
        self, subdomains: list[str]
    ) -> tuple[list[str], dict[str, None], dict[str, None]]:
        """
        Single-pass classification of raw subdomains into three buckets.
        All buckets use dict for O(1) dedup.
        clean is returned sorted.
        """
        clean: dict[str, None] = {}
        wildcards: dict[str, None] = {}
        out_of_scope: dict[str, None] = {}

        for sub in subdomains:
            sub = sub.strip().lower()

            if not sub:
                continue

            if sub.startswith(self.WILDCARD_PREFIX):
                wildcards[sub] = None
            elif not self._in_scope(sub):
                out_of_scope[sub] = None
            else:
                clean[sub] = None

        return sorted(clean), wildcards, out_of_scope

    # ------------------------------------------------------------------
    # Wildcard handling
    # ------------------------------------------------------------------

    @staticmethod
    def _finalize_wildcards(wildcards: dict[str, None]) -> list[str]:
        """
        Strip the *. prefix (2-char slice, no regex) and sort.

        Example:
            *.mail.telekom.de -> mail.telekom.de
        """
        return sorted(w[2:] for w in wildcards)

    # ------------------------------------------------------------------
    # Scope filtering — precomputed suffixes
    # ------------------------------------------------------------------

    def _in_scope(self, subdomain: str) -> bool:
        """
        Check if the subdomain is explicitly blacklisted (out of scope),
        then check if it is within in-scope suffixes.
        """
        if subdomain in self._oos_exact or subdomain.endswith(self._oos_suffixes):
            return False

        return (
            subdomain in self._scope_exact
            or subdomain.endswith(self._scope_suffixes)
        )

    # ------------------------------------------------------------------
    # Dedup + sort
    # ------------------------------------------------------------------

    @staticmethod
    def _dedup_and_sort(subdomains: list[str]) -> list[str]:
        """
        Dedup via dict.fromkeys (preserves order, O(1) per key)
        then sort. Used only in merge() where two lists are combined.
        """
        return sorted(dict.fromkeys(subdomains))

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def _build_result(
        self,
        by_plugin: dict[str, list[str]],
        wildcards: list[str],
        out_of_scope: list[str],
    ) -> ProcessedResult:
        """Assemble the final ProcessedResult dataclass."""
        return ProcessedResult(
            by_plugin=by_plugin,
            wildcards=wildcards,
            out_of_scope=out_of_scope,
        )