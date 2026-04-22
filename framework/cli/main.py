from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import inspect
import platform
from pathlib import Path
import threading
from typing import Callable, Sequence

from framework import __version__
from framework.core import load_runtime_config
from framework.dsl.models import SuiteSpec
from framework.executor import Executor, SuiteExecutionResult
from framework.executor.execution_control import select_cases
from framework.keywords import load_keyword_libraries, load_listeners
from framework.logging import configure_runtime_logger
from framework.notify import DingTalkNotifier, EmailNotifier, SmtpConfig
from framework.page_objects.base_page import BasePage
from framework.parser import get_parser
from framework.reporting import AllureReporter, ReportContext
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
        "--exclude-tag-expr",
        default=None,
        help="Exclude cases whose tags match this expression.",
    )
    parser.add_argument(
        "--run-empty-suite",
        action="store_true",
        help="Treat empty suite after filtering as success instead of error.",
    )
    parser.add_argument(
        "--rerunfailed",
        default=None,
        help="Path to case-results.json; rerun only failed cases from that file.",
    )
    parser.add_argument(
        "--merge-results",
        default=None,
        help="Comma-separated case-results JSON files to merge and report.",
    )
    parser.add_argument(
        "--workers",
        type=_parse_workers,
        default=1,
        help="Case-level worker count; 0 or 1 keeps serial execution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate DSL, variables, keywords and arguments without starting a browser.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    dependencies: RuntimeDependencies | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.dsl_path and not args.merge_results:
        parser.error("dsl_path is required unless --merge-results is provided.")
    if args.dsl_path and args.merge_results:
        parser.error("dsl_path cannot be used with --merge-results.")
    dependencies = dependencies or _default_dependencies()
    config = load_runtime_config(args.config)

    browser = config.get("browser", args.browser)
    headless = config.get("headless", args.headless)
    implicit_wait = int(config.get("implicit_wait", 10))
    log_level = config.get("log_level", args.log_level)

    logger = dependencies.logger_factory(log_level, args.log_file)
    keyword_libraries = load_keyword_libraries(config)
    listeners = load_listeners(config)
    allowed_case_names = (
        read_failed_case_names(Path(args.rerunfailed)) if args.rerunfailed else None
    )
    report_context = ReportContext(
        browser=browser,
        headless=headless,
        python_version=platform.python_version(),
        framework_version=__version__,
        runtime_log_path=args.log_file,
        dsl_path=args.dsl_path,
    )
    if args.merge_results:
        merge_paths = parse_merge_results_argument(args.merge_results)
        suite_result = load_merged_suite_result(merge_paths)
        _write_suite_case_results(suite_result)
        _handle_reporting(args, suite_result, dependencies, logger, report_context)
        _handle_notifications(args, suite_result, config, dependencies)
        return 0 if _suite_passed(suite_result) else 1

    suite = _load_suite(args.dsl_path)
    selected_cases = select_cases(
        suite.cases,
        include_expr=args.include_tag_expr,
        exclude_expr=args.exclude_tag_expr,
        allowed_case_names=allowed_case_names,
    )
    if not selected_cases:
        if not args.run_empty_suite:
            raise ValueError("Suite contains no runnable cases after filtering.")
        suite_result = SuiteExecutionResult(
            name=suite.name,
            total_cases=0,
            passed_cases=0,
            failed_cases=0,
            case_results=[],
        )
        _write_suite_case_results(suite_result)
        _handle_reporting(args, suite_result, dependencies, logger, report_context)
        _handle_notifications(args, suite_result, config, dependencies)
        return 0

    if args.dry_run:
        executor = _build_executor(
            dependencies,
            actions=None,
            logger=logger,
            keyword_libraries=keyword_libraries,
            listeners=listeners,
            dry_run=True,
        )
        suite_result = executor.run_file(
            args.dsl_path,
            include_tag_expr=args.include_tag_expr,
            exclude_tag_expr=args.exclude_tag_expr,
            run_empty_suite=args.run_empty_suite,
            allowed_case_names=allowed_case_names,
            workers=args.workers,
        )
        _write_suite_case_results(suite_result)
        _handle_reporting(args, suite_result, dependencies, logger, report_context)
        _handle_notifications(args, suite_result, config, dependencies)
        return 0 if _suite_passed(suite_result) else 1

    driver_manager = dependencies.driver_manager_factory()
    driver_config = DriverConfig(
        browser=browser,
        headless=headless,
        implicit_wait=implicit_wait,
    )
    if args.workers <= 1:
        sessions = BrowserSessionManager(
            driver_manager=driver_manager,
            driver_config=driver_config,
            actions_factory=dependencies.actions_factory,
        )
        try:
            actions = SessionActionsProxy(sessions)
            executor = _build_executor(
                dependencies,
                actions=actions,
                logger=logger,
                keyword_libraries=keyword_libraries,
                listeners=listeners,
                dry_run=False,
            )
            suite_result = executor.run_file(
                args.dsl_path,
                include_tag_expr=args.include_tag_expr,
                exclude_tag_expr=args.exclude_tag_expr,
                run_empty_suite=args.run_empty_suite,
                allowed_case_names=allowed_case_names,
                workers=args.workers,
            )
            _write_suite_case_results(suite_result)
            _handle_reporting(args, suite_result, dependencies, logger, report_context)
            _handle_notifications(args, suite_result, config, dependencies)
        finally:
            sessions.close_all()
    else:
        actions = _ThreadLocalSessionActionsProxy(
            driver_manager=driver_manager,
            driver_config=driver_config,
            actions_factory=dependencies.actions_factory,
        )
        try:
            executor = _build_executor(
                dependencies,
                actions=actions,
                logger=logger,
                keyword_libraries=keyword_libraries,
                listeners=listeners,
                dry_run=False,
            )
            suite_result = executor.run_file(
                args.dsl_path,
                include_tag_expr=args.include_tag_expr,
                exclude_tag_expr=args.exclude_tag_expr,
                run_empty_suite=args.run_empty_suite,
                allowed_case_names=allowed_case_names,
                workers=args.workers,
            )
            _write_suite_case_results(suite_result)
            _handle_reporting(args, suite_result, dependencies, logger, report_context)
            _handle_notifications(args, suite_result, config, dependencies)
        finally:
            actions.quit_all()

    return 0 if _suite_passed(suite_result) else 1


def _build_executor(
    dependencies: RuntimeDependencies,
    *,
    actions: object,
    logger: object,
    keyword_libraries: list[object],
    listeners: list[object],
    dry_run: bool,
) -> Executor:
    signature = inspect.signature(dependencies.executor_factory)
    accepts_varargs = any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    if accepts_varargs or len(signature.parameters) >= 5:
        return dependencies.executor_factory(
            actions,
            logger,
            keyword_libraries,
            listeners,
            dry_run,
        )
    return dependencies.executor_factory(actions, logger)


def _write_suite_case_results(suite_result: SuiteExecutionResult) -> None:
    cases = [asdict(case_result) for case_result in suite_result.case_results]
    write_case_results(
        Path("artifacts/case-results.json"),
        cases,
        suite_teardown_failed=suite_result.suite_teardown_failed,
        suite_teardown_error_message=suite_result.suite_teardown_error_message,
        suite_teardown_failure_type=suite_result.suite_teardown_failure_type,
    )


def _handle_reporting(
    args,
    suite_result: SuiteExecutionResult,
    dependencies: RuntimeDependencies,
    logger: object,
    report_context: ReportContext,
) -> None:
    if not args.allure:
        return
    reporter = dependencies.reporter_factory(args.allure_results_dir)
    reporter.write_suite_result(suite_result, context=report_context)
    reporter.write_environment_properties(report_context)
    generated = reporter.generate_html_report(output_dir=args.allure_report_dir)
    if not generated and hasattr(logger, "error"):
        logger.error("Allure report generation failed")


def _handle_notifications(
    args,
    suite_result: SuiteExecutionResult,
    config: dict,
    dependencies: RuntimeDependencies,
) -> None:
    summary = (
        f"Suite={suite_result.name}, total={suite_result.total_cases}, "
        f"passed={suite_result.passed_cases}, failed={suite_result.failed_cases}"
    )
    if args.notify_email:
        smtp = config.get("smtp")
        if not isinstance(smtp, dict):
            raise ValueError("SMTP config is required when --notify-email is enabled.")
        required_keys = {"host", "port", "username", "password", "sender", "receivers"}
        missing_keys = sorted(required_keys - smtp.keys())
        if missing_keys:
            raise ValueError(f"Missing SMTP config keys: {', '.join(missing_keys)}")
        notifier = dependencies.email_notifier_factory(
            SmtpConfig(
                host=smtp["host"],
                port=int(smtp["port"]),
                username=smtp["username"],
                password=smtp["password"],
                sender=smtp["sender"],
                receivers=list(smtp["receivers"]),
                use_ssl=bool(smtp.get("use_ssl", True)),
                timeout_seconds=int(smtp.get("timeout_seconds", 10)),
                retries=int(smtp.get("retries", 0)),
            )
        )
        notifier.send(subject="Web Automation Result", body=summary)
    if args.notify_dingtalk:
        webhook = config.get("dingtalk_webhook")
        if not webhook:
            raise ValueError(
                "DingTalk webhook is required when --notify-dingtalk is enabled."
            )
        notifier = dependencies.dingtalk_notifier_factory(str(webhook))
        retries = int(config.get("dingtalk_retries", 0))
        if hasattr(notifier, "retries"):
            notifier.retries = retries
        notifier.send(title="Web Automation Result", text=summary)


def _suite_passed(suite_result: SuiteExecutionResult) -> bool:
    return suite_result.failed_cases == 0 and not suite_result.suite_teardown_failed


def _load_suite(dsl_path: str) -> SuiteSpec:
    parser = get_parser(dsl_path)
    return parser.parse(dsl_path)


def entrypoint() -> None:
    raise SystemExit(main())
