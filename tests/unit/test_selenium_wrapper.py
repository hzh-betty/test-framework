import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from selenium.common.exceptions import TimeoutException

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

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True


class FakeAlert:
    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


class FakeSwitchTo:
    def __init__(self):
        self.frame_calls: list[object] = []
        self.window_calls: list[str] = []
        self.default_content_calls = 0
        self.parent_frame_calls = 0
        self.alert = FakeAlert()

    def frame(self, frame_reference: object):
        self.frame_calls.append(frame_reference)

    def window(self, handle: str):
        self.window_calls.append(handle)

    def default_content(self):
        self.default_content_calls += 1

    def parent_frame(self):
        self.parent_frame_calls += 1


class FakeDriver:
    def __init__(self):
        self.opened_urls: list[str] = []
        self.find_calls: list[tuple[str, str]] = []
        self.saved_paths: list[str] = []
        self.elements: dict[tuple[str, str], FakeElement] = {}
        self.window_handles: list[str] = ["main", "popup"]
        self.switch_to = FakeSwitchTo()

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

    def test_click_uses_clickable_wait_before_clicking(self):
        driver = FakeDriver()
        element = FakeElement()
        actions = SeleniumActions(driver=driver)
        with patch.object(actions, "_find_clickable", return_value=element) as finder:
            actions.click("id=submit")

        finder.assert_called_once_with("id=submit", action="click")
        self.assertTrue(element.clicked)

    def test_type_uses_visible_wait_before_input(self):
        driver = FakeDriver()
        element = FakeElement()
        actions = SeleniumActions(driver=driver)
        with patch.object(actions, "_find_visible", return_value=element) as finder:
            actions.type("id=username", "demo")

        finder.assert_called_once_with("id=username", action="type")
        self.assertTrue(element.cleared)
        self.assertEqual(element.sent_value, "demo")

    def test_assert_text_raises_on_mismatch(self):
        driver = FakeDriver()
        driver.elements[("id", "welcome")] = FakeElement(text="Hello")
        actions = SeleniumActions(driver=driver)
        with self.assertRaises(AssertionError):
            actions.assert_text("id=welcome", "Welcome")

    def test_click_empty_locator_reports_click_action(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)

        with self.assertRaisesRegex(ValueError, "action='click'.*empty locator"):
            actions.click(" ")

    def test_type_empty_locator_reports_type_action(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)

        with self.assertRaisesRegex(ValueError, "action='type'.*empty locator"):
            actions.type(" ", "demo")

    def test_assert_text_empty_locator_reports_assert_text_action(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)

        with self.assertRaisesRegex(ValueError, "action='assert_text'.*empty locator"):
            actions.assert_text(" ", "Welcome")

    def test_screenshot_uses_driver_api(self):
        driver = FakeDriver()
