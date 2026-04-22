from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Iterable, Sequence

from framework.executor.models import CaseExecutionResult, SuiteExecutionResult


@dataclass(frozen=True)
class NotificationSummary:
    title: str
    text: str
    attachments: list[str]


class NotificationDispatcher:
    def __init__(self, channels: Sequence[tuple[str, str, object]]):
        self.channels = list(channels)

    def send(
        self,
        *,
        result: SuiteExecutionResult,
        statistics: dict | None = None,
        attachments: Sequence[str] | None = None,
    ) -> list[str]:
        summary = build_notification_summary(
            result,
            statistics=statistics or {},
            attachments=list(attachments or []),
        )
        errors: list[str] = []
        for name, trigger, notifier in self.channels:
            if not _trigger_matches(trigger, result):
                continue
            try:
                _send(notifier, summary)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        return errors


def build_notification_summary(
    result: SuiteExecutionResult,
    *,
    statistics: dict | None = None,
    attachments: Sequence[str] | None = None,
) -> NotificationSummary:
    overall = (statistics or {}).get("overall", {})
    pass_rate = overall.get("pass_rate")
    if pass_rate is None:
        pass_rate = 0.0 if result.total_cases == 0 else round(
            result.passed_cases / result.total_cases * 100,
            2,
        )
    title = "Web Automation Result"
    lines = [
        f"套件: {result.name}",
        f"总数: {result.total_cases}",
        f"通过: {result.passed_cases}",
        f"失败: {result.failed_cases}",
        f"通过率: {pass_rate}%",
    ]
    failed_cases = [case for case in result.case_results if not case.passed]
    if failed_cases:
        lines.append("")
        lines.append("失败用例:")
        for case in failed_cases:
            lines.extend(_failed_case_lines(case))
    module_stats = (statistics or {}).get("module")
    if isinstance(module_stats, dict):
        lines.append("")
        lines.append("按模块统计:")
        for module, stats in sorted(module_stats.items()):
            if not isinstance(stats, dict):
                continue
            lines.append(
                f"- {module}: {stats.get('passed', 0)}/{stats.get('total', 0)} "
                f"通过, 通过率 {stats.get('pass_rate', 0.0)}%"
            )
    return NotificationSummary(
        title=title,
        text="\n".join(lines),
        attachments=list(attachments or []),
    )


def _failed_case_lines(case: CaseExecutionResult) -> Iterable[str]:
    yield (
        f"- {case.name} | module={case.module or 'unassigned'} "
        f"| owner={case.owner or 'unassigned'} "
        f"| failure_type={case.failure_type or 'unknown'}"
    )
    if case.error_message:
        yield f"  错误: {case.error_message}"
    for step in case.step_results:
        if step.passed:
            continue
        if step.screenshot_path:
            yield f"  截图: {step.screenshot_path}"
        if step.page_source_path:
            yield f"  Page Source: {step.page_source_path}"


def _trigger_matches(trigger: str, result: SuiteExecutionResult) -> bool:
    normalized = trigger.strip().lower()
    failed = result.failed_cases > 0 or result.suite_teardown_failed
    if normalized == "always":
        return True
    if normalized == "on_failure":
        return failed
    if normalized == "on_success":
        return not failed
    raise ValueError(f"Unsupported notification trigger: {trigger}")


def _send(notifier: object, summary: NotificationSummary) -> None:
    send = getattr(notifier, "send")
    signature = inspect.signature(send)
    parameters = signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()):
        send(
            title=summary.title,
            text=summary.text,
            subject=summary.title,
            body=summary.text,
            attachment_paths=summary.attachments,
        )
        return
    if "subject" in parameters:
        send(
            subject=summary.title,
            body=summary.text,
            attachment_paths=summary.attachments,
        )
        return
    send(title=summary.title, text=summary.text)
