class FindarcError(Exception):
    """Base exception for all findarc errors."""


class AuthError(FindarcError):
    """Authentication failed or API key missing."""


class NotFoundError(FindarcError):
    """Requested resource not found (404)."""


class PermissionError(FindarcError):
    """Current agent is not allowed to perform this action (403)."""


class APIError(FindarcError):
    """Unexpected HTTP error from the server."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


class ConfigError(FindarcError):
    """Configuration file missing or malformed."""
