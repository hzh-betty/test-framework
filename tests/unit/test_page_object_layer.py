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

    def wait_clickable(self, locator: str, timeout: int = 10):
        self.calls.append(("wait_clickable", locator, timeout))

    def wait_text(self, locator: str, expected: str, timeout: int = 10):
        self.calls.append(("wait_text", locator, expected, timeout))

    def wait_url_contains(self, text: str, timeout: int = 10):
        self.calls.append(("wait_url_contains", text, timeout))

    def assert_element_visible(self, locator: str, timeout: int = 10):
        self.calls.append(("assert_element_visible", locator, timeout))

    def assert_element_contains(self, locator: str, expected: str):
        self.calls.append(("assert_element_contains", locator, expected))

    def select(self, locator: str, option_text: str):
        self.calls.append(("select", locator, option_text))

    def hover(self, locator: str):
        self.calls.append(("hover", locator))

    def switch_frame(self, frame: str):
        self.calls.append(("switch_frame", frame))

    def switch_window(self, target: str):
        self.calls.append(("switch_window", target))

    def accept_alert(self, timeout: int = 10):
        self.calls.append(("accept_alert", timeout))

    def upload_file(self, locator: str, file_path: str):
        self.calls.append(("upload_file", locator, file_path))


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

    def test_base_page_delegates_extended_actions(self):
        actions = FakeActions()
        page = BasePage(actions=actions)

        page.wait_clickable("id=submit", timeout=3)
        page.wait_text("id=status", "Done", timeout=4)
        page.wait_url_contains("/dashboard", timeout=5)
        page.assert_element_visible("id=title", timeout=6)
        page.assert_element_contains("id=title", "Welcome")
        page.select("id=country", "China")
        page.hover("id=menu")
        page.switch_frame("id=frame-main")
        page.switch_window("1")
        page.accept_alert(timeout=7)
        page.upload_file("id=upload", "fixtures/demo.txt")

        self.assertEqual(
            actions.calls,
            [
                ("wait_clickable", "id=submit", 3),
                ("wait_text", "id=status", "Done", 4),
                ("wait_url_contains", "/dashboard", 5),
                ("assert_element_visible", "id=title", 6),
                ("assert_element_contains", "id=title", "Welcome"),
                ("select", "id=country", "China"),
                ("hover", "id=menu"),
                ("switch_frame", "id=frame-main"),
                ("switch_window", "1"),
                ("accept_alert", 7),
                ("upload_file", "id=upload", "fixtures/demo.txt"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
