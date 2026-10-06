"""内置 Web 关键字。

这些方法故意保持很薄：它们只把 DSL 中的字符串参数转换成浏览器动作需要的
对象，真正的 Selenium 细节都留在 ``webtest_core.browser``。
"""

from __future__ import annotations

from webtest_core.browser import parse_locator
from webtest_core.browser.actions import _validate_target
from webtest_core.keywords import keyword
from webtest_core.dsl.durations import seconds


_seconds = seconds


class WebKeywordLibrary:
    """基于 Selenium 浏览器动作的默认关键字库。"""

    def __init__(self, actions, *, default_timeout: float = 10):
        self.actions = actions
        self.default_timeout = default_timeout

    def validate_call(self, name: str, arguments: dict) -> None:
        for parameter in ("url", "text", "fragment", "alias", "path"):
            if parameter in arguments and not isinstance(arguments[parameter], str):
                raise ValueError(f"{parameter} must be a string")
        if "locator" in arguments:
            parse_locator(arguments["locator"])
        if "timeout" in arguments:
            arguments["timeout"] = seconds(arguments["timeout"], self.default_timeout)
        if name in {"Switch Frame", "Switch Window"}:
            target = arguments["target"]
            _validate_target(target)
            if name == "Switch Frame" and isinstance(target, str) and target not in {"default", "parent"} and not target.isdigit():
                parse_locator(target)

    @keyword("Open")
    def open(self, url: str):
        self.actions.open(url)

    @keyword("New Browser")
    def new_browser(self, alias: str = "default"):
        self.actions.new_browser(alias)

    @keyword("Switch Browser")
    def switch_browser(self, alias: str):
        self.actions.switch_browser(alias)

    @keyword("Click")
    def click(self, locator: str):
        self.actions.click(parse_locator(locator))

    @keyword("Type Text")
    def type_text(self, locator: str, text: str):
        self.actions.type_text(parse_locator(locator), text)

    @keyword("Clear")
    def clear(self, locator: str):
        self.actions.clear(parse_locator(locator))

    @keyword("Assert Text")
    def assert_text(self, locator: str, text: str):
        self.actions.assert_text(parse_locator(locator), text)

    @keyword("Wait Visible")
    def wait_visible(self, locator: str, timeout: str | int | float | None = None):
        self.actions.wait_visible(parse_locator(locator), seconds(timeout, self.default_timeout))

    @keyword("Wait Clickable")
    def wait_clickable(self, locator: str, timeout: str | int | float | None = None):
        self.actions.wait_clickable(parse_locator(locator), seconds(timeout, self.default_timeout))

    @keyword("Wait Not Visible")
    def wait_not_visible(self, locator: str, timeout: str | int | float | None = None):
        self.actions.wait_not_visible(parse_locator(locator), seconds(timeout, self.default_timeout))

    @keyword("Wait Gone")
    def wait_gone(self, locator: str, timeout: str | int | float | None = None):
        self.actions.wait_not_visible(parse_locator(locator), seconds(timeout, self.default_timeout))

    @keyword("Wait Text")
    def wait_text(self, locator: str, text: str, timeout: str | int | float | None = None):
        self.actions.wait_text(parse_locator(locator), text, seconds(timeout, self.default_timeout))

    @keyword("Wait URL Contains")
    def wait_url_contains(self, fragment: str, timeout: str | int | float | None = None):
        self.actions.wait_url_contains(fragment, seconds(timeout, self.default_timeout))

    @keyword("Assert Element Visible")
    def assert_element_visible(self, locator: str):
        self.actions.assert_element_visible(parse_locator(locator))

    @keyword("Assert Element Contains")
    def assert_element_contains(self, locator: str, text: str):
        self.actions.assert_element_contains(parse_locator(locator), text)

    @keyword("Assert URL Contains")
    def assert_url_contains(self, fragment: str):
        self.actions.assert_url_contains(fragment)

    @keyword("Assert Title Contains")
    def assert_title_contains(self, text: str):
        self.actions.assert_title_contains(text)

    @keyword("Select")
    def select(self, locator: str, text: str):
        self.actions.select(parse_locator(locator), text)

    @keyword("Hover")
    def hover(self, locator: str):
        self.actions.hover(parse_locator(locator))

    @keyword("Switch Frame")
    def switch_frame(self, target: str | int):
        self.actions.switch_frame(target)

    @keyword("Switch Window")
    def switch_window(self, target: str | int):
        self.actions.switch_window(target)

    @keyword("Accept Alert")
    def accept_alert(self):
        self.actions.accept_alert()

    @keyword("Upload File")
    def upload_file(self, locator: str, path: str):
        self.actions.upload_file(parse_locator(locator), path)

    @keyword("Screenshot")
    def screenshot(self, path: str):
        self.actions.screenshot(path)

    @keyword("Close Browser")
    def close_browser(self):
        self.actions.close_browser()
