from __future__ import annotations

from .decorators import keyword, library
from framework.selenium.locators import Locator


@library
class WebKeywordLibrary:
    def __init__(self, page: object):
        self.page = page

    @keyword("Open")
    def open(self, url: str) -> None:
        self.page.open(url)

    @keyword("Click")
    def click(self, locator: Locator) -> None:
        self.page.click(locator.raw)

    @keyword("Type Text")
    def type_text(self, locator: Locator, text: str) -> None:
        self.page.type(locator.raw, text)

    @keyword("Clear")
    def clear(self, locator: Locator) -> None:
        self.page.clear(locator.raw)

    @keyword("Wait Visible")
    def wait_visible(self, locator: Locator, timeout: float = 10) -> None:
        self.page.wait_visible(locator.raw, timeout=timeout)

    @keyword("Wait Not Visible")
    def wait_not_visible(self, locator: Locator, timeout: float = 10) -> None:
        self.page.wait_not_visible(locator.raw, timeout=timeout)

    @keyword("Wait Gone")
    def wait_gone(self, locator: Locator, timeout: float = 10) -> None:
        self.page.wait_gone(locator.raw, timeout=timeout)

    @keyword("Wait Clickable")
    def wait_clickable(self, locator: Locator, timeout: float = 10) -> None:
        self.page.wait_clickable(locator.raw, timeout=timeout)

    @keyword("Wait Text")
    def wait_text(self, locator: Locator, expected: str, timeout: float = 10) -> None:
        self.page.wait_text(locator.raw, expected, timeout=timeout)

    @keyword("Wait URL Contains")
    def wait_url_contains(self, fragment: str, timeout: float = 10) -> None:
        self.page.wait_url_contains(fragment, timeout=timeout)

    @keyword("Assert Text")
    def assert_text(self, locator: Locator, expected: str) -> None:
        self.page.assert_text(locator.raw, expected)

    @keyword("Assert Element Visible")
    def assert_element_visible(self, locator: Locator, timeout: float = 10) -> None:
        self.page.assert_element_visible(locator.raw, timeout=timeout)

    @keyword("Assert Element Contains")
    def assert_element_contains(self, locator: Locator, expected: str) -> None:
        self.page.assert_element_contains(locator.raw, expected)

    @keyword("Assert URL Contains")
    def assert_url_contains(self, fragment: str) -> None:
        self.page.assert_url_contains(fragment)

    @keyword("Assert Title Contains")
    def assert_title_contains(self, expected: str) -> None:
        self.page.assert_title_contains(expected)

    @keyword("Select")
    def select(self, locator: Locator, option_text: str) -> None:
        self.page.select(locator.raw, option_text)

    @keyword("Hover")
    def hover(self, locator: Locator) -> None:
        self.page.hover(locator.raw)

    @keyword("Switch Frame")
    def switch_frame(self, frame_reference: str) -> None:
        self.page.switch_frame(frame_reference)

    @keyword("Switch Window")
    def switch_window(self, window_reference: str) -> None:
        self.page.switch_window(window_reference)

    @keyword("Accept Alert")
    def accept_alert(self, timeout: float = 10) -> None:
        self.page.accept_alert(timeout=timeout)

    @keyword("Upload File")
    def upload_file(self, locator: Locator, file_path: str) -> None:
        self.page.upload_file(locator.raw, file_path)

    @keyword("Screenshot")
    def screenshot(self, path: str) -> None:
        self.page.screenshot(path)

    @keyword("New Browser")
    def new_browser(self, alias: str = "default") -> None:
        self.page.new_browser(alias)

    @keyword("Switch Browser")
    def switch_browser(self, alias: str) -> None:
        self.page.switch_browser(alias)

    @keyword("Close Browser")
    def close_browser(self, alias: str | None = None) -> None:
        self.page.close_browser(alias)


def build_builtin_registry(page: object) -> "KeywordRegistry":
    from .registry import KeywordRegistry

    registry = KeywordRegistry()
    registry.register_library(WebKeywordLibrary(page))
    return registry
