from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import inspect
import platform
from pathlib import Path
import subprocess
import threading
from typing import Callable, Sequence

from framework import __version__
from framework.core import load_runtime_config
from framework.dsl.models import SuiteSpec
from framework.executor import CaseExecutionResult, Executor, SuiteExecutionResult
from framework.executor.execution_control import select_cases
from framework.keywords import load_keyword_libraries, load_listeners
from framework.logging import configure_runtime_logger
from framework.notify import (
    DingTalkNotifier,
    EmailNotifier,
    NotificationDispatcher,
    SmtpConfig,
    WebhookNotifier,
)
from framework.page_objects.base_page import BasePage
from framework.parser import get_parser
from framework.reporting import AllureReporter, ReportContext, build_statistics, write_statistics
from framework.reporting.case_results import read_failed_case_names, write_case_results
from framework.reporting.result_merge import (
    load_merged_suite_result,
    parse_merge_results_argument,
)
from framework.selenium import (
    BrowserSessionManager,
    DriverConfig,
    DriverManager,
    SeleniumActions,
    SessionActionsProxy,
)


@dataclass(frozen=True)
class RuntimeDependencies:
    driver_manager_factory: Callable[[], DriverManager]
    actions_factory: Callable[[object], SeleniumActions]
    executor_factory: Callable[..., Executor]
    reporter_factory: Callable[[str], AllureReporter]
    logger_factory: Callable[[str, str], object]
    email_notifier_factory: Callable[[SmtpConfig], EmailNotifier]
    dingtalk_notifier_factory: Callable[[str], DingTalkNotifier]


class _ThreadLocalSessionActionsProxy:
    def __init__(
        self,
        driver_manager: DriverManager,
        driver_config: DriverConfig,
        actions_factory: Callable[[object], SeleniumActions],
    ):
        self._driver_manager = driver_manager
        self._driver_config = driver_config
        self._actions_factory = actions_factory
        self._thread_state = threading.local()
        self._session_lock = threading.Lock()
        self._session_managers: list[BrowserSessionManager] = []

    def _actions(self) -> SessionActionsProxy:
        proxy = getattr(self._thread_state, "actions", None)
        if proxy is not None:
            return proxy
        with self._session_lock:
            proxy = getattr(self._thread_state, "actions", None)
            if proxy is not None:
                return proxy
            sessions = BrowserSessionManager(
                driver_manager=self._driver_manager,
                driver_config=self._driver_config,
                actions_factory=self._actions_factory,
            )
            self._session_managers.append(sessions)
            proxy = SessionActionsProxy(sessions)
            self._thread_state.actions = proxy
            return proxy

    def __getattr__(self, name: str):
        return getattr(self._actions(), name)

    def quit_all(self) -> None:
        for sessions in self._session_managers:
            sessions.close_all()
        self._session_managers.clear()


def _default_dependencies() -> RuntimeDependencies:
    return RuntimeDependencies(
        driver_manager_factory=lambda: DriverManager(),
        actions_factory=lambda driver: SeleniumActions(driver=driver),
        executor_factory=lambda actions, logger, keyword_libraries=None, listeners=None, dry_run=False: Executor(
            page_factory=lambda: BasePage(actions=actions),
            logger=logger,
            keyword_libraries=list(keyword_libraries or []),
            listeners=list(listeners or []),
            dry_run=dry_run,
        ),
        reporter_factory=lambda results_dir: AllureReporter(results_dir=results_dir),
        logger_factory=lambda level, log_file: configure_runtime_logger(
            level=level,
            log_file=log_file,
        ),
        email_notifier_factory=lambda config: EmailNotifier(config=config),
        dingtalk_notifier_factory=lambda webhook: DingTalkNotifier(webhook=webhook),
    )


def _parse_workers(value: str) -> int:
    try:
        workers = int(value)
    except ValueError as exc:  # pragma: no cover - argparse enforces string input
        raise argparse.ArgumentTypeError("workers must be an integer.") from exc
    if workers < 0:
        raise argparse.ArgumentTypeError("workers must be greater than or equal to 0.")
    return workers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webtest-framework",
        description="Execute DSL-driven web automation tests.",
    )
    parser.add_argument(
        "dsl_path",
        nargs="?",
        help="Path to XML/YAML/JSON test case file.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to runtime config file.",
    )
    parser.add_argument(
        "--browser",
        choices=("chrome", "firefox", "edge"),
        default="chrome",
        help="Browser type used by Selenium.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Runtime log level.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--allure",
        action="store_true",
        help="Write Allure artifacts and generate report.",
    )
    parser.add_argument(
        "--allure-results-dir",
        default="artifacts/allure-results",
        help="Allure results output directory.",
    )
    parser.add_argument(
        "--allure-report-dir",
        default="artifacts/allure-report",
        help="Generated Allure HTML report directory.",
    )
    parser.add_argument(
        "--log-file",
        default="artifacts/runtime.log",
        help="Runtime log file path.",
    )
    parser.add_argument(
        "--notify-email",
        action="store_true",
        help="Send execution summary by email. Requires SMTP config file.",
    )
    parser.add_argument(
        "--notify-dingtalk",
        action="store_true",
        help="Send execution summary to DingTalk webhook in config file.",
    )
    parser.add_argument(
        "--include-tag-expr",
        default=None,
        help="Include only cases whose tags match this expression.",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=None,
        help="Run only cases whose module matches one of the provided values.",
    )
    parser.add_argument(
        "--case-type",
        action="append",
        default=None,
        help="Run only cases whose type matches one of the provided values.",
    )
    parser.add_argument(
        "--priority",
        action="append",
        default=None,
        help="Run only cases whose priority matches one of the provided values.",
    )
    parser.add_argument(
        "--owner",
        action="append",
        default=None,
        help="Run only cases whose owner matches one of the provided values.",
