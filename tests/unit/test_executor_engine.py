import unittest
from dataclasses import dataclass
import tempfile
from pathlib import Path
import threading
import time

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.executor.runner import Executor


@dataclass
class FakePage:
    calls: list[tuple]

    def open(self, url: str):
        self.calls.append(("open", url))

    def click(self, locator: str):
        self.calls.append(("click", locator))

    def type(self, locator: str, value: str):
        self.calls.append(("type", locator, value))

    def assert_text(self, locator: str, expected: str):
        self.calls.append(("assert_text", locator, expected))
        if expected == "FAIL":
            raise AssertionError("text mismatch")

    def wait_visible(self, locator: str, timeout: int = 10):
        self.calls.append(("wait_visible", locator, timeout))

    def screenshot(self, path: str):
        if "/screenshots/" not in path:
            self.calls.append(("screenshot", path))

    def wait_clickable(self, locator: str, timeout: int = 10):
        self.calls.append(("wait_clickable", locator, timeout))

    def wait_text(self, locator: str, expected: str, timeout: int = 10):
        self.calls.append(("wait_text", locator, expected, timeout))

    def wait_url_contains(self, fragment: str, timeout: int = 10):
        self.calls.append(("wait_url_contains", fragment, timeout))

    def assert_element_visible(self, locator: str, timeout: int = 10):
        self.calls.append(("assert_element_visible", locator, timeout))
