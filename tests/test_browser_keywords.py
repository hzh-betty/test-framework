import pytest

from webtest_core.browser import Locator, parse_locator
from webtest_core.keywords import KeywordRegistry
from webtest_core.keywords.web import WebKeywordLibrary


class FakeActions:
    def __init__(self):
        self.calls = []

    def open(self, url: str):
        self.calls.append(("open", url))

    def click(self, locator: Locator):
        self.calls.append(("click", locator.by, locator.value))

    def type_text(self, locator: Locator, text: str):
        self.calls.append(("type_text", locator.by, locator.value, text))

    def assert_text(self, locator: Locator, text: str):
        self.calls.append(("assert_text", locator.by, locator.value, text))

    def wait_visible(self, locator: Locator, timeout=10):
        self.calls.append(("wait_visible", locator.by, locator.value, timeout))

    def wait_clickable(self, locator: Locator, timeout=10):
        self.calls.append(("wait_clickable", locator.by, locator.value, timeout))

    def wait_text(self, locator: Locator, text: str, timeout=10):
        self.calls.append(("wait_text", locator.by, locator.value, text, timeout))

    def wait_url_contains(self, fragment: str, timeout=10):
        self.calls.append(("wait_url_contains", fragment, timeout))

    def new_browser(self, alias: str = "default"):
        self.calls.append(("new_browser", alias))

    def switch_browser(self, alias: str):
        self.calls.append(("switch_browser", alias))

    def close_browser(self):
        self.calls.append(("close_browser",))


def test_parse_locator_supports_strict_prefixes_and_default_css():
    assert parse_locator("id=username") == Locator(by="id", value="username")
    assert parse_locator("css=.submit") == Locator(by="css selector", value=".submit")
    assert parse_locator("text=登录") == Locator(by="xpath", value="//*[normalize-space(.)='登录']")
    assert parse_locator("partial_text=登录") == Locator(by="xpath", value="//*[contains(normalize-space(.), '登录')]")
    assert parse_locator("testid=submit") == Locator(by="css selector", value="[data-testid='submit']")
    assert parse_locator("data-testid=submit") == Locator(by="css selector", value="[data-testid='submit']")
    assert parse_locator(".default") == Locator(by="css selector", value=".default")

    with pytest.raises(ValueError, match="Unknown locator strategy"):
        parse_locator("bad=value")


def test_web_keyword_library_registers_browser_actions():
    actions = FakeActions()
    registry = KeywordRegistry.from_libraries([WebKeywordLibrary(actions)])

    registry.run("Open", ["https://example.test"])
    registry.run("Click", ["id=submit"])
    registry.run("Type Text", ["id=username", "demo"])
    registry.run("Assert Text", ["css=.title", "Welcome"])
    registry.run("Close Browser")

    assert actions.calls == [
        ("open", "https://example.test"),
        ("click", "id", "submit"),
        ("type_text", "id", "username", "demo"),
        ("assert_text", "css selector", ".title", "Welcome"),
        ("close_browser",),
    ]


def test_web_keywords_support_robot_names_timeout_units_and_browser_sessions():
    actions = FakeActions()
    registry = KeywordRegistry.from_libraries([WebKeywordLibrary(actions)])

    registry.run("wait-visible", ["id=panel"], {"timeout": "500ms"})
    registry.run("wait_clickable", ["id=submit"], {"timeout": "1 minute"})
    registry.run("Wait Text", ["css=.message", "完成"], {"timeout": "2s"})
    registry.run("Wait URL Contains", ["/dashboard"], {"timeout": "3s"})
    registry.run("New Browser", ["admin"])
    registry.run("Switch Browser", ["admin"])

    assert actions.calls == [
        ("wait_visible", "id", "panel", 0.5),
        ("wait_clickable", "id", "submit", 60.0),
        ("wait_text", "css selector", ".message", "完成", 2.0),
        ("wait_url_contains", "/dashboard", 3.0),
        ("new_browser", "admin"),
        ("switch_browser", "admin"),
    ]
