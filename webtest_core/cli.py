"""CLI 组装与独立运行目录；所有执行失败都进入本次报告。"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import platform
import subprocess
import sys
from typing import Sequence
from uuid import uuid4

from webtest_core import __version__
from webtest_core.browser import BrowserConfig, BrowserSessionActions
from webtest_core.dsl import DslValidationError, RuntimeConfig, load_runtime_config, load_suite
from webtest_core.integrations.notifications import DingtalkSender, EmailSender, FeishuSender, NotificationChannel, NotificationDispatcher, WebhookSender
from webtest_core.keywords import KeywordRegistry
from webtest_core.keywords.http import HttpKeywordLibrary
from webtest_core.keywords.web import WebKeywordLibrary
from webtest_core.redaction import Redactor
from webtest_core.reports import build_statistics, merge_case_results, read_failed_case_names, write_allure_results, write_case_results, write_html_report, write_statistics
from webtest_core.reports.io import write_json
from webtest_core.runtime import CaseResult, SuiteExecutor, SuiteResult, select_cases
from webtest_core.runtime.deploy import run_deploy_command


def _positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="webtest", description="Run YAML WebTest suites.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run a YAML suite.")
    run.add_argument("suite", nargs="?")
    run.add_argument("--config")
    run.add_argument("--browser", choices=("chrome", "firefox", "edge"))
    run.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--workers", type=_positive_int, default=1)
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
    run.add_argument("--html-report", action=argparse.BooleanOptionalAction, default=None)
    run.add_argument("--allure", action=argparse.BooleanOptionalAction, default=None)
    run.add_argument("--notify", action="store_true")
    run.add_argument("--deploy", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = Path(args.output_dir).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
    output_dir = output_root / "runs" / run_id
    output_dir.mkdir(parents=True)
    manifest = {"run_id": run_id, "directory": str(output_dir), "status": "running"}
    write_json(output_root / "latest-run.json", manifest)
    config = RuntimeConfig()
    result = SuiteResult(Path(args.suite).stem if args.suite else "Merged")
    redactor = Redactor()
    logger = None
    executor = None
    interrupted = False
    log_path = output_dir / "runtime.log"
    try:
        config = load_runtime_config(args.config)
        redactor.collect(config.model_dump())
        configured_path = Path(config.logging.file) if config.logging.file else Path("runtime.log")
        log_path = configured_path if configured_path.is_absolute() else output_dir / configured_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.Logger(f"webtest.{run_id}", level=config.logging.level)
        handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.info("Run %s started; dry_run=%s", run_id, args.dry_run)
        if args.merge_results:
            if args.suite or args.deploy or args.rerun_failed:
                raise DslValidationError("merge-results cannot be combined with suite, deploy or rerun-failed")
            result = merge_case_results([part.strip() for part in args.merge_results.split(",") if part.strip()])
        else:
            if not args.suite:
                raise DslValidationError("suite path is required unless --merge-results is provided")
            suite = load_suite(args.suite)
            result.name = suite.name
            redactor.collect_suite(suite.model_dump())
            allowed = read_failed_case_names(args.rerun_failed, suite_name=suite.name,
                case_names=[case.name for case in suite.cases]) if args.rerun_failed else None
            executor = SuiteExecutor(lambda: _build_registry(args, config), dry_run=args.dry_run,
                                     redactor=redactor, output_dir=output_dir)
            filters = dict(include_tag_expr=args.include_tag_expr, exclude_tag_expr=args.exclude_tag_expr,
                           modules=_values(args.module), case_types=_values(args.case_type), priorities=_values(args.priority),
                           owners=_values(args.owner), allowed_case_names=allowed)
            if args.deploy and not args.dry_run:
                selected = select_cases(suite.cases, **filters)
                if not selected and not args.run_empty_suite:
                    raise DslValidationError("Suite contains no runnable cases after filtering.")
                executor.validate_suite(suite, selected)
                deploy_failure = _run_deploy_if_needed(args, config, suite, selected, redactor)
                if deploy_failure is not None:
                    result = deploy_failure
                else:
                    result = executor.run_suite(suite, allowed_case_names={case.name for case in selected},
                        workers=args.workers, run_empty_suite=args.run_empty_suite)
            else:
                result = executor.run_suite(suite, **filters, workers=args.workers, run_empty_suite=args.run_empty_suite)
    except KeyboardInterrupt:
        interrupted = True
        result = getattr(executor, "last_result", result)
        result.error_message = result.error_message or "Run interrupted"
        result.failure_type = "action"
    except Exception as exc:
        result.error_message = redactor.redact(str(exc))
        result.failure_type = "validation" if isinstance(exc, (DslValidationError, ValueError)) else "action"
    try:
        _write_outputs(args, output_dir, result, config, redactor=redactor, logger=logger, runtime_log_path=log_path)
        manifest["status"] = "interrupted" if interrupted else ("passed" if result.passed else "failed")
        return 130 if interrupted else (0 if result.passed else 1)
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
        return 130
    except Exception:
        manifest["status"] = "output_failed"
        raise
    finally:
        try:
            write_json(output_root / "latest-run.json", manifest)
        finally:
            if logger:
                for handler in logger.handlers[:]:
                    handler.close()
                    logger.removeHandler(handler)


def entrypoint() -> None:
    raise SystemExit(main())


def _build_registry(args, config: RuntimeConfig) -> KeywordRegistry:
    actions = BrowserSessionActions.create(BrowserConfig(browser=args.browser or config.browser,
        headless=config.headless if args.headless is None else args.headless, implicit_wait=config.timeouts.implicit_wait))
    return KeywordRegistry.from_libraries([WebKeywordLibrary(actions, default_timeout=config.timeouts.explicit_wait), HttpKeywordLibrary()],
                                         diagnostics=actions.diagnostics, cleanup=actions.close_all)


def _write_outputs(args, output_dir: Path, result: SuiteResult, config: RuntimeConfig | None = None, *,
                   redactor: Redactor | None = None, logger=None, runtime_log_path=None) -> None:
    config = config or RuntimeConfig()
    redactor = redactor or Redactor(config.model_dump(), result.to_dict())
    stats = build_statistics(result, redactor=redactor)
    # 先保存执行结果；通知及可选报告失败不会丢失本次结果。
    write_case_results(output_dir / "case-results.json", result, redactor=redactor)
    write_statistics(output_dir / "statistics.json", result, statistics=stats, redactor=redactor)
    if args.notify and not args.dry_run:
        errors = NotificationDispatcher(_notification_channels(config)).send(result, statistics=stats, redactor=redactor)
        result.notification_errors = redactor.redact(errors)
        for error in result.notification_errors:
            print(f"Notification failed: {error}", file=sys.stderr)
        write_case_results(output_dir / "case-results.json", result, redactor=redactor)
    if logger:
        logger.info("Result: %s", redactor.redact(json.dumps(result.to_dict(), ensure_ascii=False)))
        for handler in logger.handlers:
            handler.flush()
    html_enabled = config.reports.html if args.html_report is None else args.html_report
    allure_enabled = config.reports.allure if args.allure is None else args.allure
    if html_enabled:
        write_html_report(output_dir / "html-report", result, stats, redactor=redactor)
    if allure_enabled:
        write_allure_results(output_dir / "allure-results", result, browser=args.browser or config.browser,
            headless=config.headless if args.headless is None else args.headless,
            python_version=platform.python_version(), framework_version=__version__,
            runtime_log_path=str(runtime_log_path) if runtime_log_path else None,
            dsl_path=args.suite if args.suite and not args.merge_results else None, redactor=redactor)


def _run_deploy_if_needed(args, config: RuntimeConfig, suite, cases=None, redactor=None) -> SuiteResult | None:
    if not args.deploy or args.dry_run:
        return None
    redactor = redactor or Redactor(config.model_dump(), suite.model_dump())
    for command in config.pipeline.deploy.commands:
        error = None
        try:
            completed = run_deploy_command(command, timeout=config.pipeline.deploy.timeout)
            if completed.returncode != 0:
                details = (completed.stderr or completed.stdout)[-4000:]
                error = f"deploy command failed with exit code {completed.returncode}: {command}\n{details}"
        except subprocess.TimeoutExpired as exc:
            error = f"deploy command timed out after {config.pipeline.deploy.timeout}s: {command}"
        except OSError as exc:
            error = f"deploy command failed: {exc}"
        if error is not None:
            error = redactor.redact(error)
            blocked = [CaseResult(case.name, False, suite=suite.name, blocked=True, error_message=error,
                failure_type="deploy", module=case.module, type=case.type, priority=case.priority,
                owner=case.owner, tags=list(case.tags)) for case in (suite.cases if cases is None else cases)]
            return SuiteResult(suite.name, case_results=blocked, error_message=error, failure_type="deploy")
    return None


def _notification_channels(config: RuntimeConfig) -> list[NotificationChannel]:
    channels = []
    for channel in config.notifications.channels:
        sender = None
        if channel.enabled:
            if channel.type == "email":
                sender = EmailSender(**channel.smtp.model_dump())
            else:
                sender_type = {"dingtalk": DingtalkSender, "feishu": FeishuSender, "webhook": WebhookSender}[channel.type]
                sender = sender_type(channel.webhook)
        channels.append(NotificationChannel(channel.type, channel.enabled, channel.trigger, channel.retries, sender))
    return channels


def _values(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    parsed = {part.strip() for value in values for part in value.split(",") if part.strip()}
    if not parsed:
        raise DslValidationError("filter value must not be empty")
    return parsed
