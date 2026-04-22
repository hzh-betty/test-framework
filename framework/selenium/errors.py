from __future__ import annotations


class WebTestError(RuntimeError):
    """Base class for framework-level web action errors."""


class ActionError(WebTestError):
    """Raised when a web action cannot be executed."""


class LocatorError(ActionError):
    """Raised when a locator is invalid or cannot be resolved."""


class WaitTimeoutError(ActionError, TimeoutError):
    """Raised when an explicit wait times out."""


class BrowserSessionError(ActionError):
    """Raised when browser session management fails."""


class AssertionMismatch(ActionError, AssertionError):
    """Raised when a web assertion fails."""
