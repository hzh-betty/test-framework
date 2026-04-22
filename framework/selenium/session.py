from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .driver_manager import DriverConfig, DriverManager
from .errors import BrowserSessionError


ActionsFactory = Callable[[object], object]


@dataclass
class BrowserSession:
    alias: str
    driver: object
    actions: object


class BrowserSessionManager:
    def __init__(
        self,
        driver_manager: DriverManager,
        driver_config: DriverConfig,
        actions_factory: ActionsFactory,
    ):
        self._driver_manager = driver_manager
        self._driver_config = driver_config
        self._actions_factory = actions_factory
        self._sessions: dict[str, BrowserSession] = {}
        self._current_alias: str | None = None

    @property
    def current_alias(self) -> str | None:
        return self._current_alias

    def open_browser(self, alias: str = "default") -> object:
        normalized = self._normalize_alias(alias)
        if normalized in self._sessions:
            raise BrowserSessionError(f"Browser session alias '{alias}' already exists.")
        driver = self._driver_manager.create_driver(self._driver_config)
        actions = self._actions_factory(driver)
        self._sessions[normalized] = BrowserSession(normalized, driver, actions)
        self._current_alias = normalized
        return actions

    def switch_browser(self, alias: str) -> object:
        normalized = self._normalize_alias(alias)
        if normalized not in self._sessions:
            raise BrowserSessionError(f"Non-existing browser session alias '{alias}'.")
        self._current_alias = normalized
        return self._sessions[normalized].actions

    def close_browser(self, alias: str | None = None) -> None:
        normalized = self._normalize_alias(alias or self._current_alias)
        session = self._sessions.pop(normalized, None)
        if session is None:
            raise BrowserSessionError(f"Non-existing browser session alias '{alias}'.")
        self._driver_manager.quit_driver(session.driver)
        if self._current_alias == normalized:
            self._current_alias = next(iter(self._sessions), None)

    def current_actions(self, create_default: bool = False) -> object:
        if self._current_alias is None:
            if create_default:
                return self.open_browser("default")
            raise BrowserSessionError("No current browser session.")
        return self._sessions[self._current_alias].actions

    def close_all(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        self._current_alias = None
        for session in sessions:
            self._driver_manager.quit_driver(session.driver)

    def _normalize_alias(self, alias: str | None) -> str:
        if not alias or not str(alias).strip():
            raise BrowserSessionError("Browser session alias must not be empty.")
        return str(alias).strip()


class SessionActionsProxy:
    def __init__(self, sessions: BrowserSessionManager):
        self.sessions = sessions

    @property
    def driver(self):
        return getattr(self._actions(), "driver", None)

    @property
    def current_alias(self) -> str | None:
        return self.sessions.current_alias

    def new_browser(self, alias: str = "default") -> None:
        self.sessions.open_browser(alias or "default")

    def switch_browser(self, alias: str) -> None:
        self.sessions.switch_browser(alias)

    def close_browser(self, alias: str | None = None) -> None:
        self.sessions.close_browser(alias)

    def __getattr__(self, name: str):
        return getattr(self._actions(), name)

    def _actions(self):
        return self.sessions.current_actions(create_default=True)
