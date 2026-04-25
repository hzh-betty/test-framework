from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import unittest
from pathlib import Path

from unittest.mock import patch

from framework.executor.models import CaseExecutionResult, SuiteExecutionResult
from framework.reporting.case_results import write_case_results
from framework.cli.main import RuntimeDependencies, build_parser, main


class FakeDriverManager:
    def __init__(self):
        self.created = False
        self.quitted = False
        self.created_drivers = []
        self.quitted_drivers = []
        self.driver = object()

    def create_driver(self, _config):
        self.created = True
        self.created_drivers.append(self.driver)
        return self.driver

    def quit_driver(self, driver):
        self.quitted = True
        self.quitted_drivers.append(driver)


class FakeExecutor:
    def __init__(self, suite_result: SuiteExecutionResult):
        self.suite_result = suite_result
        self.run_file_calls = []

    def run_file(self, dsl_path: str, **kwargs):
        self.run_file_calls.append((dsl_path, kwargs))
        return self.suite_result


class FakeReporter:
    def __init__(self, generated: bool = True):
        self.written = False
        self.generated = False
        self._generated_value = generated

    def write_suite_result(self, _result, context=None):
        self.written = True
        return Path("artifacts/allure-results/executor-summary.json")

    def write_environment_properties(self, _context):
        return Path("artifacts/allure-results/environment.properties")

    def generate_html_report(self, output_dir):
        self.generated = True
        return self._generated_value


class FakeNotifier:
    def __init__(self):
        self.sent = False

    def send(self, **_kwargs):
        self.sent = True


class FakeLogger:
    def __init__(self):
        self.info_messages = []
        self.error_messages = []

    def info(self, message: str):
        self.info_messages.append(message)

    def error(self, message: str):
        self.error_messages.append(message)


class TrackingDriver:
    def __init__(self, name: str):
        self.name = name
        self.opened = []

    def get(self, url: str):
        self.opened.append(url)


class TrackingDriverManager:
