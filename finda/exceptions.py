class FindaError(Exception):
    """Base exception for all finda errors."""


class AuthError(FindaError):
    """Authentication failed or API key missing."""


class NetworkError(FindaError):
    """Network transport or connectivity failure."""


class NotFoundError(FindaError):
    """Requested resource not found (404)."""


class PermissionError(FindaError):
    """Current agent is not allowed to perform this action (403)."""


class APIError(FindaError):
    """Unexpected HTTP error from the server."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


class ConfigError(FindaError):
    """Configuration file missing or malformed."""
