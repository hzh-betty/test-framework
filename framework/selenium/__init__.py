"""Selenium wrappers used by executor and page objects."""

from .driver_manager import DriverConfig, DriverManager
from .errors import (
    ActionError,
    AssertionMismatch,
    BrowserSessionError,
    LocatorError,
    WaitTimeoutError,
)
from .locators import Locator
from .session import BrowserSessionManager, SessionActionsProxy
from .wrapper import SeleniumActions

__all__ = [
    "ActionError",
    "AssertionMismatch",
    "BrowserSessionError",
    "BrowserSessionManager",
    "DriverConfig",
    "DriverManager",
    "Locator",
    "LocatorError",
    "SeleniumActions",
    "SessionActionsProxy",
    "WaitTimeoutError",
]
