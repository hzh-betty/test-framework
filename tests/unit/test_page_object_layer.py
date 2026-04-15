import unittest

from framework.page_objects.base_page import BasePage


class FakeActions:
    def __init__(self):
        self.calls = []

    def open(self, url: str):
        self.calls.append(("open", url))

    def click(self, locator: str):
        self.calls.append(("click", locator))

    def type(self, locator: str, value: str):
        self.calls.append(("type", locator, value))

    def assert_text(self, locator: str, expected: str):
        self.calls.append(("assert_text", locator, expected))

    def wait_visible(self, locator: str, timeout: int = 10):
        self.calls.append(("wait_visible", locator, timeout))

    def screenshot(self, path: str):
        self.calls.append(("screenshot", path))


class TestPageObjectLayer(unittest.TestCase):
    def test_base_page_delegates_to_selenium_actions(self):
        actions = FakeActions()
        page = BasePage(actions=actions)

        page.open("https://example.test/login")
        page.type("id=username", "demo")
        page.click("id=submit")
        page.assert_text("id=title", "Welcome")
        page.wait_visible("id=title", timeout=5)
        page.screenshot("artifacts/failure.png")

        self.assertEqual(
            actions.calls,
            [
                ("open", "https://example.test/login"),
                ("type", "id=username", "demo"),
                ("click", "id=submit"),
                ("assert_text", "id=title", "Welcome"),
                ("wait_visible", "id=title", 5),
                ("screenshot", "artifacts/failure.png"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
