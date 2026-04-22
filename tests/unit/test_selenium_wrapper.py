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
        actions = SeleniumActions(driver=driver)
        with tempfile.TemporaryDirectory() as tmpdir:
            screenshot = Path(tmpdir) / "failed.png"
            actions.screenshot(str(screenshot))
        self.assertEqual(driver.saved_paths[-1], str(screenshot))

    def test_wait_clickable_uses_explicit_wait(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)
        element = FakeElement()
        with (
            patch("selenium.webdriver.support.ui.WebDriverWait") as wait_cls,
            patch(
                "selenium.webdriver.support.expected_conditions.element_to_be_clickable"
            ) as clickable,
        ):
            wait_cls.return_value.until.return_value = element
            clickable.return_value = MagicMock()
            result = actions.wait_clickable("id=submit", timeout=7)

        wait_cls.assert_called_once_with(driver, 7)
        clickable.assert_called_once_with(("id", "submit"))
        self.assertIs(result, element)

    def test_wait_clickable_timeout_uses_consistent_error_message(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)
        with patch("selenium.webdriver.support.ui.WebDriverWait") as wait_cls:
            wait_cls.return_value.until.side_effect = TimeoutException("timed out")
            with self.assertRaisesRegex(
                TimeoutError,
                "wait_clickable.*locator='id=submit'.*timeout=3s",
            ):
                actions.wait_clickable("id=submit", timeout=3)

    def test_wait_text_uses_expected_condition(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)
        with (
            patch("selenium.webdriver.support.ui.WebDriverWait") as wait_cls,
            patch(
                "selenium.webdriver.support.expected_conditions.text_to_be_present_in_element"
            ) as condition,
        ):
            marker = MagicMock()
            condition.return_value = marker
            actions.wait_text("id=status", "Done", timeout=9)

        wait_cls.assert_called_once_with(driver, 9)
        condition.assert_called_once_with(("id", "status"), "Done")
        wait_cls.return_value.until.assert_called_once_with(marker)

    def test_wait_url_contains_uses_expected_condition(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)
        with (
            patch("selenium.webdriver.support.ui.WebDriverWait") as wait_cls,
            patch("selenium.webdriver.support.expected_conditions.url_contains") as condition,
        ):
            marker = MagicMock()
            condition.return_value = marker
            actions.wait_url_contains("/dashboard", timeout=5)

        wait_cls.assert_called_once_with(driver, 5)
        condition.assert_called_once_with("/dashboard")
        wait_cls.return_value.until.assert_called_once_with(marker)

    def test_assert_element_visible_raises_assertion_error_on_timeout(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)
        with patch.object(actions, "wait_visible", side_effect=TimeoutError("boom")):
            with self.assertRaisesRegex(
                AssertionError,
                "assert_element_visible.*locator='id=title'.*timeout=4s",
            ):
                actions.assert_element_visible("id=title", timeout=4)

    def test_assert_element_contains_raises_on_mismatch(self):
        driver = FakeDriver()
        driver.elements[("id", "title")] = FakeElement(text="Welcome")
        actions = SeleniumActions(driver=driver)

        with self.assertRaisesRegex(
            AssertionError,
            "assert_element_contains.*expected to contain 'Admin'",
        ):
            actions.assert_element_contains("id=title", "Admin")

    def test_select_uses_visible_text(self):
        driver = FakeDriver()
        driver.elements[("id", "country")] = FakeElement()
        actions = SeleniumActions(driver=driver)
        with patch("selenium.webdriver.support.ui.Select") as select_cls:
            actions.select("id=country", "China")

        select_cls.assert_called_once()
        select_cls.return_value.select_by_visible_text.assert_called_once_with("China")

    def test_hover_uses_action_chains(self):
        driver = FakeDriver()
        driver.elements[("id", "menu")] = FakeElement()
        actions = SeleniumActions(driver=driver)
        with patch("selenium.webdriver.common.action_chains.ActionChains") as chains_cls:
            chain = chains_cls.return_value
            chain.move_to_element.return_value = chain
            actions.hover("id=menu")

        chains_cls.assert_called_once_with(driver)
        chain.move_to_element.assert_called_once()
        chain.perform.assert_called_once()

    def test_switch_frame_supports_locator(self):
        driver = FakeDriver()
        frame_el = FakeElement()
        driver.elements[("id", "content-frame")] = frame_el
        actions = SeleniumActions(driver=driver)

        actions.switch_frame("id=content-frame")

        self.assertEqual(driver.switch_to.frame_calls, [frame_el])

    def test_switch_window_supports_index_target(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)

        actions.switch_window("1")

        self.assertEqual(driver.switch_to.window_calls, ["popup"])

    def test_accept_alert_waits_then_accepts(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)
        with (
            patch("selenium.webdriver.support.ui.WebDriverWait") as wait_cls,
            patch("selenium.webdriver.support.expected_conditions.alert_is_present") as condition,
        ):
            marker = MagicMock()
            condition.return_value = marker
            wait_cls.return_value.until.return_value = driver.switch_to.alert
            actions.accept_alert(timeout=6)

        wait_cls.assert_called_once_with(driver, 6)
        wait_cls.return_value.until.assert_called_once_with(marker)
        self.assertTrue(driver.switch_to.alert.accepted)

    def test_upload_file_sends_path(self):
        driver = FakeDriver()
        upload = FakeElement()
        driver.elements[("id", "upload")] = upload
        actions = SeleniumActions(driver=driver)

        actions.upload_file("id=upload", "fixtures/demo.txt")

        self.assertEqual(upload.sent_value, "fixtures/demo.txt")

    def test_upload_file_failure_uses_consistent_error_message(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)
        failing_upload = MagicMock()
        failing_upload.send_keys.side_effect = OSError("disk unavailable")
        with patch.object(actions, "_find_visible", return_value=failing_upload):
            with self.assertRaisesRegex(
                RuntimeError,
                "upload_file.*locator='id=upload'.*target='fixtures/demo.txt'.*disk unavailable",
            ):
                actions.upload_file("id=upload", "fixtures/demo.txt")

    def test_upload_file_locator_failure_uses_consistent_error_message(self):
        driver = FakeDriver()
        actions = SeleniumActions(driver=driver)

        with self.assertRaisesRegex(
            RuntimeError,
            "upload_file.*locator='id=upload'.*target='fixtures/demo.txt'",
        ):
            actions.upload_file("id=upload", "fixtures/demo.txt")


if __name__ == "__main__":
    unittest.main()
