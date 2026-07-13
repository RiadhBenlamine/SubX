"""Exception classes for subdomain discovery plugins."""


class PluginException(Exception):
    """Base exception class for all subdomain enumeration plugins."""


class PluginAuthError(PluginException):
    """Raised when an API key is unauthorized or invalid (401/403)."""


class PluginRateLimitError(PluginException):
    """Raised when a rate limit is hit after max retries (429)."""

    def __init__(self, message: str, partial_subdomains: list[str] | None = None):
        super().__init__(message)
        self.partial_subdomains = partial_subdomains or []


class PluginUnavailableError(PluginException):
    """Raised when the target source is transiently down or returns 5xx/timeouts."""
