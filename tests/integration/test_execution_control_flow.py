import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from framework.cli.main import RuntimeDependencies, main
from framework.executor.runner import Executor
from framework.page_objects.base_page import BasePage
from framework.reporting.case_results import read_case_results, write_case_results


class FakeDriverManager:
    def __init__(self):
        self.created = False
        self.quitted = False
        self.driver = object()

    def create_driver(self, _config):
        self.created = True
        return self.driver

    def quit_driver(self, _driver):
        self.quitted = True


class GuardDriverManager:
    def create_driver(self, _config):
        raise AssertionError("driver must not be created in this flow")

    def quit_driver(self, _driver):
        return None


class FakeActions:
    def __init__(self):
        self.calls: list[tuple] = []

    def open(self, url: str):
        self.calls.append(("open", url))

    def type(self, locator: str, value: str):
        self.calls.append(("type", locator, value))

    def click(self, locator: str):
        self.calls.append(("click", locator))

    def assert_text(self, locator: str, expected: str):
        self.calls.append(("assert_text", locator, expected))

    def wait_visible(self, locator: str, timeout: int = 10):
        self.calls.append(("wait_visible", locator, timeout))

    def screenshot(self, path: str):
        self.calls.append(("screenshot", path))


class FakeLogger:
    def info(self, _message: str):
