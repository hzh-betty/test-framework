"""``webtest`` 命令行入口。

CLI 是组装层：读取配置、构建关键字库、执行套件或合并结果，然后写出报告。
业务规则放在被调用的模块中，避免命令解析文件变成新的“大泥球”。
"""

from __future__ import annotations

import argparse
import platform
import subprocess
from pathlib import Path
from typing import Sequence

from webtest_core import __version__
from webtest_core.browser import BrowserConfig, BrowserSessionActions
from webtest_core.dsl import RuntimeConfig, load_runtime_config, load_suite
from webtest_core.integrations.notifications import (
    DingtalkSender,
    EmailSender,
    FeishuSender,
    NotificationChannel,
    NotificationDispatcher,
    WebhookSender,
)
from webtest_core.keywords import KeywordRegistry
from webtest_core.keywords.http import HttpKeywordLibrary
from webtest_core.keywords.web import WebKeywordLibrary
from webtest_core.reports import (
    build_statistics,
    merge_case_results,
    read_failed_case_names,
    write_allure_results,
    write_case_results,
    write_html_report,
    write_statistics,
)
from webtest_core.runtime import CaseResult, SuiteExecutor, SuiteResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="webtest", description="Run YAML WebTest suites.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run a YAML suite.")
    run.add_argument("suite", nargs="?")
    run.add_argument("--config")
    run.add_argument("--browser", choices=("chrome", "firefox", "edge"))
    run.add_argument("--headless", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--include-tag-expr")
    run.add_argument("--exclude-tag-expr")
    run.add_argument("--module", action="append")
    run.add_argument("--case-type", action="append")
    run.add_argument("--priority", action="append")
    run.add_argument("--owner", action="append")
    run.add_argument("--rerun-failed", dest="rerun_failed")
    run.add_argument("--run-empty-suite", action="store_true")
    run.add_argument("--merge-results")
    run.add_argument("--output-dir", default="artifacts")
    run.add_argument("--html-report", action="store_true")
    run.add_argument("--allure", action="store_true")
    run.add_argument("--notify", action="store_true")
    run.add_argument("--deploy", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "run":
        raise ValueError(f"Unknown command: {args.command}")
    config = load_runtime_config(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.merge_results:
        result = merge_case_results([part.strip() for part in args.merge_results.split(",") if part.strip()])
        _write_outputs(args, output_dir, result, config=config)
        return 0 if result.failed_cases == 0 else 1

    if not args.suite:
        raise ValueError("suite path is required unless --merge-results is provided")

    suite = load_suite(args.suite)
    allowed_case_names = read_failed_case_names(args.rerun_failed) if args.rerun_failed else None
    deploy_failure = _run_deploy_if_needed(args, config, suite)
    if deploy_failure is not None:
        _write_outputs(args, output_dir, deploy_failure)
        return 1

    registry = _build_registry(args, config)
    try:
        result = SuiteExecutor(registry=registry, dry_run=args.dry_run).run_suite(
            suite,
            include_tag_expr=args.include_tag_expr,
            exclude_tag_expr=args.exclude_tag_expr,
            modules=_values(args.module),
            case_types=_values(args.case_type),
            priorities=_values(args.priority),
            owners=_values(args.owner),
            allowed_case_names=allowed_case_names,
            workers=max(args.workers, 1),
            run_empty_suite=args.run_empty_suite,
        )
    finally:
        close_all = getattr(getattr(registry, "_webtest_actions", None), "close_all", None)
        if callable(close_all):
            close_all()
    _write_outputs(args, output_dir, result, config=config)
    return 0 if result.failed_cases == 0 else 1


def entrypoint() -> None:
    raise SystemExit(main())


def _build_registry(args, config: RuntimeConfig) -> KeywordRegistry:
    if args.dry_run:
        actions = _DryRunActions()
    else:
        browser = args.browser or config.browser
        actions = BrowserSessionActions.create(
            BrowserConfig(
                browser=browser,
                headless=args.headless or config.headless,
                implicit_wait=config.timeouts.implicit_wait,
            )
        )
    registry = KeywordRegistry.from_libraries([WebKeywordLibrary(actions), HttpKeywordLibrary()])
    setattr(registry, "_webtest_actions", actions)
    return registry


def _write_outputs(args, output_dir: Path, result: SuiteResult, config: RuntimeConfig | None = None) -> None:
    write_case_results(output_dir / "case-results.json", result)
    stats = build_statistics(result)
    write_statistics(output_dir / "statistics.json", result)
    if args.html_report:
        write_html_report(output_dir / "html-report", result, stats)
    if args.allure:
        write_allure_results(
            output_dir / "allure-results",
            result,
            browser=args.browser or (config.browser if config else "unknown"),
            headless=bool(args.headless or (config.headless if config else False)),
            python_version=platform.python_version(),
            framework_version=__version__,
            runtime_log_path=str(output_dir / "runtime.log"),
            dsl_path=getattr(args, "suite", None),
        )
    if args.notify and config is not None:
        NotificationDispatcher(_notification_channels(config)).send(result, statistics=stats)


def _run_deploy_if_needed(args, config: RuntimeConfig, suite) -> SuiteResult | None:
    if not args.deploy:
        return None
    for command in config.pipeline.deploy.commands:
        completed = subprocess.run(command, shell=True, text=True, capture_output=True)
        if completed.returncode != 0:
            cases = [
                CaseResult(
                    name=case.name,
                    passed=False,
                    error_message=f"deploy command failed with exit code {completed.returncode}: {command}",
                    failure_type="deploy",
                    module=case.module,
                    type=case.type,
                    priority=case.priority,
                    owner=case.owner,
                    tags=list(case.tags),
                )
                for case in suite.cases
            ]
            return SuiteResult(
                name=suite.name,
                total_cases=len(cases),
                passed_cases=0,
                failed_cases=len(cases),
                case_results=cases,
