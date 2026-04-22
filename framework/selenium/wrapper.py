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
                    detail=str(exc),
                )
            ) from exc

    def hover(self, locator: str) -> None:
        from selenium.webdriver.common.action_chains import ActionChains

        try:
            element = self._find(locator, action="hover")
            ActionChains(self.driver).move_to_element(element).perform()
        except Exception as exc:
            raise RuntimeError(
                self._format_action_error(
                    action="hover",
                    locator=locator,
                    detail=str(exc),
                )
            ) from exc

    def switch_frame(self, frame_reference: str) -> None:
        normalized = frame_reference.strip().lower()
        try:
            if normalized in {"default", "default_content"}:
                self.driver.switch_to.default_content()
                return
            if normalized in {"parent", "parent_frame"}:
                self.driver.switch_to.parent_frame()
                return
            if frame_reference.isdigit():
                self.driver.switch_to.frame(int(frame_reference))
                return
            if "=" in frame_reference:
                self.driver.switch_to.frame(
                    self._find(frame_reference, action="switch_frame")
                )
                return
            self.driver.switch_to.frame(frame_reference)
        except Exception as exc:
            raise RuntimeError(
                self._format_action_error(
                    action="switch_frame",
                    target=frame_reference,
                    detail=str(exc),
                )
            ) from exc

    def switch_window(self, window_reference: str) -> None:
        try:
            if window_reference.isdigit():
                index = int(window_reference)
                handles = list(self.driver.window_handles)
                if index < 0 or index >= len(handles):
                    raise ValueError(f"window index {index} is out of range")
                self.driver.switch_to.window(handles[index])
                return
            self.driver.switch_to.window(window_reference)
        except Exception as exc:
            raise RuntimeError(
                self._format_action_error(
                    action="switch_window",
                    target=window_reference,
                    detail=str(exc),
                )
            ) from exc

    def accept_alert(self, timeout: int = 10) -> None:
        from selenium.webdriver.support import expected_conditions as ec

        alert = self._wait_for(
            action="accept_alert",
            condition=ec.alert_is_present(),
            timeout=timeout,
            target="alert",
        )
        alert.accept()

    def upload_file(self, locator: str, file_path: str) -> None:
        try:
            element = self._find_visible(locator, action="upload_file")
            element.send_keys(file_path)
        except Exception as exc:
            raise RuntimeError(
                self._format_action_error(
                    action="upload_file",
                    locator=locator,
                    target=file_path,
                    detail=str(exc),
                )
            ) from exc

    def screenshot(self, path: str) -> None:
        screenshot_path = Path(path)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.driver.save_screenshot(str(screenshot_path)):
            raise RuntimeError(f"Failed to save screenshot to '{screenshot_path}'.")

    def _find(self, locator: str, action: str = "find_element"):
        parsed = self._parse_locator(locator, action=action)
        try:
            return self.driver.find_element(parsed.by, parsed.value)
        except Exception as exc:
            raise RuntimeError(
                self._format_action_error(
                    action=action,
                    locator=locator,
                    detail=str(exc),
                )
            ) from exc

    def _find_visible(self, locator: str, action: str):
        from selenium.webdriver.support import expected_conditions as ec

        parsed = self._parse_locator(locator, action=action)
        return self._wait_for(
            action=action,
            condition=ec.visibility_of_element_located((parsed.by, parsed.value)),
            timeout=10,
            locator=locator,
        )

    def _find_clickable(self, locator: str, action: str):
        from selenium.webdriver.support import expected_conditions as ec

        parsed = self._parse_locator(locator, action=action)
        return self._wait_for(
            action=action,
            condition=ec.element_to_be_clickable((parsed.by, parsed.value)),
            timeout=10,
            locator=locator,
        )

    def _parse_locator(self, locator: str, action: str) -> Locator:
        if not locator.strip():
            raise ValueError(
                self._format_action_error(action=action, locator=locator, detail="empty locator")
            )
        return Locator.parse(locator)

    def _wait_for(
        self,
        action: str,
        condition: object,
        timeout: int,
        locator: str | None = None,
        target: str | None = None,
    ):
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.support.ui import WebDriverWait

        try:
            return WebDriverWait(self.driver, timeout).until(condition)
        except TimeoutException as exc:
            raise WaitTimeoutError(
                self._format_action_error(
                    action=action,
                    locator=locator,
                    target=target,
                    timeout=timeout,
                    detail="condition not met before timeout",
                )
            ) from exc

    def _format_action_error(
        self,
        action: str,
        locator: str | None = None,
        target: str | None = None,
        timeout: int | None = None,
        detail: str | None = None,
    ) -> str:
        parts = [f"action='{action}'"]
        if locator is not None:
            parts.append(f"locator='{locator}'")
        if target is not None:
            parts.append(f"target='{target}'")
        if timeout is not None:
            parts.append(f"timeout={timeout}s")
        if detail:
            parts.append(detail)
        return " | ".join(parts)
