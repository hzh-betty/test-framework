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

    def clear(self, locator: str) -> None:
        self.actions.clear(locator)

    def assert_text(self, locator: str, expected: str) -> None:
        self.actions.assert_text(locator, expected)

    def wait_visible(self, locator: str, timeout: int = 10):
        return self.actions.wait_visible(locator, timeout=timeout)

    def wait_not_visible(self, locator: str, timeout: int = 10):
        return self.actions.wait_not_visible(locator, timeout=timeout)

    def wait_gone(self, locator: str, timeout: int = 10):
        return self.actions.wait_gone(locator, timeout=timeout)

    def wait_clickable(self, locator: str, timeout: int = 10):
        return self.actions.wait_clickable(locator, timeout=timeout)

    def wait_text(self, locator: str, expected: str, timeout: int = 10):
        return self.actions.wait_text(locator, expected, timeout=timeout)

    def wait_url_contains(self, fragment: str, timeout: int = 10):
        return self.actions.wait_url_contains(fragment, timeout=timeout)

    def assert_element_visible(self, locator: str, timeout: int = 10):
        return self.actions.assert_element_visible(locator, timeout=timeout)

    def assert_element_contains(self, locator: str, expected: str) -> None:
        self.actions.assert_element_contains(locator, expected)

    def assert_url_contains(self, fragment: str) -> None:
        self.actions.assert_url_contains(fragment)

    def assert_title_contains(self, expected: str) -> None:
        self.actions.assert_title_contains(expected)

    def select(self, locator: str, option_text: str) -> None:
        self.actions.select(locator, option_text)

    def hover(self, locator: str) -> None:
        self.actions.hover(locator)

    def switch_frame(self, frame_reference: str) -> None:
        self.actions.switch_frame(frame_reference)

    def switch_window(self, window_reference: str) -> None:
        self.actions.switch_window(window_reference)

    def accept_alert(self, timeout: int = 10) -> None:
        self.actions.accept_alert(timeout=timeout)

    def upload_file(self, locator: str, file_path: str) -> None:
        self.actions.upload_file(locator, file_path)

    def screenshot(self, path: str) -> None:
        self.actions.screenshot(path)

    def new_browser(self, alias: str = "default") -> None:
        self.actions.new_browser(alias)

    def switch_browser(self, alias: str) -> None:
        self.actions.switch_browser(alias)

    def close_browser(self, alias: str | None = None) -> None:
        self.actions.close_browser(alias)
