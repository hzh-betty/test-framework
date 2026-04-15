from __future__ import annotations

from framework.selenium.wrapper import SeleniumActions


class BasePage:
    def __init__(self, actions: SeleniumActions):
        self.actions = actions

    def open(self, url: str) -> None:
        self.actions.open(url)

    def click(self, locator: str) -> None:
        self.actions.click(locator)

    def type(self, locator: str, value: str) -> None:
        self.actions.type(locator, value)

    def assert_text(self, locator: str, expected: str) -> None:
        self.actions.assert_text(locator, expected)

    def wait_visible(self, locator: str, timeout: int = 10):
        return self.actions.wait_visible(locator, timeout=timeout)

    def screenshot(self, path: str) -> None:
        self.actions.screenshot(path)
