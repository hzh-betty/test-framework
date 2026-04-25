from __future__ import annotations

from pathlib import Path

from .errors import AssertionMismatch, WaitTimeoutError
from .locators import Locator


class SeleniumActions:
    def __init__(self, driver: object):
        self.driver = driver

    def open(self, url: str) -> None:
        self.driver.get(url)

    def click(self, locator: str) -> None:
        self._find_clickable(locator, action="click").click()

    def type(self, locator: str, value: str) -> None:
        element = self._find_visible(locator, action="type")
        element.clear()
        element.send_keys(value)

    def clear(self, locator: str) -> None:
        self._find_visible(locator, action="clear").clear()

    def assert_text(self, locator: str, expected: str) -> None:
        actual = self._find(locator, action="assert_text").text
        if actual != expected:
            raise AssertionMismatch(
                f"Text assertion failed for '{locator}': expected '{expected}', got '{actual}'"
            )

    def wait_visible(self, locator: str, timeout: int = 10):
        from selenium.webdriver.support import expected_conditions as ec

        parsed = self._parse_locator(locator, action="wait_visible")
        return self._wait_for(
            action="wait_visible",
            condition=ec.visibility_of_element_located((parsed.by, parsed.value)),
            timeout=timeout,
            locator=locator,
        )

    def wait_not_visible(self, locator: str, timeout: int = 10):
        from selenium.webdriver.support import expected_conditions as ec

        parsed = self._parse_locator(locator, action="wait_not_visible")
        return self._wait_for(
            action="wait_not_visible",
            condition=ec.invisibility_of_element_located((parsed.by, parsed.value)),
            timeout=timeout,
            locator=locator,
        )

    def wait_gone(self, locator: str, timeout: int = 10):
        return self.wait_not_visible(locator, timeout=timeout)

    def wait_clickable(self, locator: str, timeout: int = 10):
        from selenium.webdriver.support import expected_conditions as ec

        parsed = self._parse_locator(locator, action="wait_clickable")
        return self._wait_for(
            action="wait_clickable",
            condition=ec.element_to_be_clickable((parsed.by, parsed.value)),
            timeout=timeout,
            locator=locator,
        )

    def wait_text(self, locator: str, expected: str, timeout: int = 10):
        from selenium.webdriver.support import expected_conditions as ec

        parsed = self._parse_locator(locator, action="wait_text")
        return self._wait_for(
            action="wait_text",
            condition=ec.text_to_be_present_in_element((parsed.by, parsed.value), expected),
            timeout=timeout,
            locator=locator,
        )

    def wait_url_contains(self, fragment: str, timeout: int = 10):
        from selenium.webdriver.support import expected_conditions as ec

        return self._wait_for(
            action="wait_url_contains",
            condition=ec.url_contains(fragment),
            timeout=timeout,
            target=fragment,
        )

    def assert_element_visible(self, locator: str, timeout: int = 10):
        try:
            return self.wait_visible(locator, timeout=timeout)
        except TimeoutError as exc:
            raise AssertionMismatch(
                self._format_action_error(
                    action="assert_element_visible",
                    locator=locator,
                    detail="element is not visible",
                    timeout=timeout,
                )
            ) from exc

    def assert_element_contains(self, locator: str, expected: str) -> None:
        actual = self._find(locator, action="assert_element_contains").text
        if expected not in actual:
            raise AssertionMismatch(
                self._format_action_error(
                    action="assert_element_contains",
                    locator=locator,
                    detail=f"expected to contain '{expected}', got '{actual}'",
                )
            )

    def assert_url_contains(self, fragment: str) -> None:
        current_url = getattr(self.driver, "current_url", "")
        if fragment not in current_url:
            raise AssertionMismatch(
                self._format_action_error(
                    action="assert_url_contains",
                    target=fragment,
                    detail=f"current url '{current_url}' does not contain '{fragment}'",
                )
            )

    def assert_title_contains(self, expected: str) -> None:
        title = getattr(self.driver, "title", "")
        if expected not in title:
            raise AssertionMismatch(
                self._format_action_error(
                    action="assert_title_contains",
                    target=expected,
                    detail=f"title '{title}' does not contain '{expected}'",
                )
            )

    def select(self, locator: str, option_text: str) -> None:
        from selenium.webdriver.support.ui import Select

        try:
            element = self._find_visible(locator, action="select")
            Select(element).select_by_visible_text(option_text)
        except Exception as exc:
            raise RuntimeError(
                self._format_action_error(
                    action="select",
                    locator=locator,
