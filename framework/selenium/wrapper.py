from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


LOCATOR_STRATEGIES = {
    "id": "id",
    "name": "name",
    "xpath": "xpath",
    "css": "css selector",
    "class": "class name",
    "tag": "tag name",
    "link": "link text",
    "partial_link": "partial link text",
}


@dataclass(frozen=True)
class Locator:
    by: str
    value: str

    @classmethod
    def parse(cls, raw_locator: str) -> "Locator":
        if "=" not in raw_locator:
            return cls(by=LOCATOR_STRATEGIES["css"], value=raw_locator)
        strategy, value = raw_locator.split("=", 1)
        normalized = strategy.strip().lower()
        if normalized not in LOCATOR_STRATEGIES:
            return cls(by=LOCATOR_STRATEGIES["css"], value=raw_locator)
        return cls(by=LOCATOR_STRATEGIES[normalized], value=value.strip())


class SeleniumActions:
    def __init__(self, driver: object):
        self.driver = driver

    def open(self, url: str) -> None:
        self.driver.get(url)

    def click(self, locator: str) -> None:
        self._find(locator).click()

    def type(self, locator: str, value: str) -> None:
        element = self._find(locator)
        element.clear()
        element.send_keys(value)

    def assert_text(self, locator: str, expected: str) -> None:
        actual = self._find(locator).text
        if actual != expected:
            raise AssertionError(
                f"Text assertion failed for '{locator}': expected '{expected}', got '{actual}'"
            )

    def wait_visible(self, locator: str, timeout: int = 10):
        from selenium.webdriver.support import expected_conditions as ec
        from selenium.webdriver.support.ui import WebDriverWait

        parsed = Locator.parse(locator)
        wait = WebDriverWait(self.driver, timeout)
        return wait.until(ec.visibility_of_element_located((parsed.by, parsed.value)))

    def screenshot(self, path: str) -> None:
        screenshot_path = Path(path)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.driver.save_screenshot(str(screenshot_path)):
            raise RuntimeError(f"Failed to save screenshot to '{screenshot_path}'.")

    def _find(self, locator: str):
        parsed = Locator.parse(locator)
        return self.driver.find_element(parsed.by, parsed.value)
