"""内置 Web 关键字。

这些方法故意保持很薄：它们只把 DSL 中的字符串参数转换成浏览器动作需要的
对象，真正的 Selenium 细节都留在 ``webtest_core.browser``。
"""

from __future__ import annotations

from webtest_core.browser import parse_locator
from webtest_core.keywords import keyword


def _seconds(value: str | int | float | None, default: int = 10) -> int | float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value
    text = value.strip().lower()
    if text.endswith("ms"):
        return float(text[:-2].strip()) / 1000
    if text.endswith("s"):
        return float(text[:-1].strip())
    if text.endswith("minute"):
        return float(text[: -len("minute")].strip()) * 60
    if text.endswith("minutes"):
        return float(text[: -len("minutes")].strip()) * 60
    if text.endswith("min"):
        return float(text[: -len("min")].strip()) * 60
    return float(text)


class WebKeywordLibrary:
    """基于 Selenium 浏览器动作的默认关键字库。"""

    def __init__(self, actions):
        self.actions = actions

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
        self.actions.wait_visible(parse_locator(locator), _seconds(timeout))

    @keyword("Wait Clickable")
    def wait_clickable(self, locator: str, timeout: str | int | float | None = None):
        self.actions.wait_clickable(parse_locator(locator), _seconds(timeout))

    @keyword("Wait Not Visible")
    def wait_not_visible(self, locator: str, timeout: str | int | float | None = None):
        self.actions.wait_not_visible(parse_locator(locator), _seconds(timeout))

    @keyword("Wait Gone")
    def wait_gone(self, locator: str, timeout: str | int | float | None = None):
        self.actions.wait_not_visible(parse_locator(locator), _seconds(timeout))

    @keyword("Wait Text")
    def wait_text(self, locator: str, text: str, timeout: str | int | float | None = None):
        self.actions.wait_text(parse_locator(locator), text, _seconds(timeout))

    @keyword("Wait URL Contains")
    def wait_url_contains(self, fragment: str, timeout: str | int | float | None = None):
        self.actions.wait_url_contains(fragment, _seconds(timeout))

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
    def switch_frame(self, target: str):
        self.actions.switch_frame(target)

    @keyword("Switch Window")
    def switch_window(self, target: str):
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
