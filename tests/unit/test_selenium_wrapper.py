import tempfile
import unittest
from pathlib import Path

from framework.selenium.wrapper import Locator, SeleniumActions


class FakeElement:
    def __init__(self, text: str = ""):
        self.text = text
        self.cleared = False
        self.sent_value = None
        self.clicked = False

    def clear(self):
        self.cleared = True

    def send_keys(self, value: str):
        self.sent_value = value

    def click(self):
        self.clicked = True


class FakeDriver:
    def __init__(self):
        self.opened_urls: list[str] = []
        self.find_calls: list[tuple[str, str]] = []
        self.saved_paths: list[str] = []
        self.elements: dict[tuple[str, str], FakeElement] = {}

    def get(self, url: str):
        self.opened_urls.append(url)

    def find_element(self, by: str, value: str):
        self.find_calls.append((by, value))
        return self.elements[(by, value)]

    def save_screenshot(self, path: str):
        self.saved_paths.append(path)
        return True


class TestSeleniumWrapper(unittest.TestCase):
    def test_parse_locator_supports_strategy_prefix(self):
        locator = Locator.parse("id=username")
        self.assertEqual(locator.by, "id")
        self.assertEqual(locator.value, "username")

    def test_parse_locator_defaults_to_css(self):
        locator = Locator.parse("button[type='submit']")
        self.assertEqual(locator.by, "css selector")
        self.assertEqual(locator.value, "button[type='submit']")

    def test_type_clears_then_inputs_value(self):
        driver = FakeDriver()
        element = FakeElement()
        driver.elements[("id", "username")] = element

        actions = SeleniumActions(driver=driver)
        actions.type("id=username", "demo")

        self.assertTrue(element.cleared)
        self.assertEqual(element.sent_value, "demo")

    def test_assert_text_raises_on_mismatch(self):
        driver = FakeDriver()
        driver.elements[("id", "welcome")] = FakeElement(text="Hello")
        actions = SeleniumActions(driver=driver)
        with self.assertRaises(AssertionError):
            actions.assert_text("id=welcome", "Welcome")

    def test_screenshot_uses_driver_api(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)
        with tempfile.TemporaryDirectory() as tmpdir:
            screenshot = Path(tmpdir) / "failed.png"
            actions.screenshot(str(screenshot))
        self.assertEqual(driver.saved_paths[-1], str(screenshot))


if __name__ == "__main__":
    unittest.main()
