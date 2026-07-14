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


class ToolNotFoundError(Exception):
    """Raised when a required external tool binary cannot be located."""


class ToolExecutionError(Exception):
    """Raised when an external tool exits with a non-zero status."""

    def __init__(self, name: str, returncode: int, stderr: str):
        self.name = name
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"{name} exited with code {returncode}: {stderr.strip()[:500]}")


class ToolTimeoutError(Exception):
    """Raised when an external tool exceeds its allotted runtime."""
