from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import time
from typing import Callable
from uuid import uuid4

from framework.executor.models import SuiteExecutionResult


CommandRunner = Callable[[list[str]], int]


@dataclass(frozen=True)
class ReportContext:
    browser: str
    headless: bool
    python_version: str
    framework_version: str
    runtime_log_path: str | None = None
    dsl_path: str | None = None


def _default_command_runner(command: list[str]) -> int:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return completed.returncode


class AllureReporter:
    def __init__(
        self,
        results_dir: str | Path = "artifacts/allure-results",
        command_runner: CommandRunner | None = None,
    ):
        self.results_dir = Path(results_dir)
        self.command_runner = command_runner or _default_command_runner

    def write_suite_result(
        self,
        result: SuiteExecutionResult,
        context: ReportContext | None = None,
    ) -> Path:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        summary_file = self.results_dir / "executor-summary.json"
        payload = {
            "suite": result.name,
            "total_cases": result.total_cases,
            "passed_cases": result.passed_cases,
            "failed_cases": result.failed_cases,
            "suite_teardown_failed": result.suite_teardown_failed,
            "suite_teardown_error_message": result.suite_teardown_error_message,
            "suite_teardown_failure_type": result.suite_teardown_failure_type,
        }
        summary_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for case in result.case_results:
            now = int(time.time() * 1000)
            steps = [self._build_step_payload(step) for step in case.step_results]
            attachments = self._build_attachments(context, case.name, case.step_results)
            case_payload = {
                "uuid": str(uuid4()),
                "name": case.name,
                "fullName": f"{result.name}.{case.name}",
                "status": "passed" if case.passed else "failed",
                "stage": "finished",
                "start": now,
                "stop": now,
                "statusDetails": self._build_status_details(
                    case.error_message,
                    case.failure_type,
                ),
                "labels": [
                    {"name": "suite", "value": result.name},
                    {"name": "framework", "value": "custom-webtest-framework"},
                ],
                "steps": steps,
                "attachments": attachments,
            }
            if case.failure_type:
                case_payload["labels"].append({"name": "failureType", "value": case.failure_type})
            case_file = self.results_dir / f"{case_payload['uuid']}-result.json"
            case_file.write_text(
                json.dumps(case_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return summary_file

    def _build_step_payload(self, step) -> dict:
        chain = " > ".join(step.call_chain) if getattr(step, "call_chain", None) else ""
        arguments = getattr(step, "arguments", []) or []
        argument_text = " ".join(str(argument) for argument in arguments)
        name = getattr(step, "keyword_name", getattr(step, "action", "step"))
        if argument_text:
            name = f"{name} {argument_text}"
        if chain:
            name = f"[{chain}] {name}"
        diagnostics = self._build_step_diagnostics(step)
        parameters = self._build_step_parameters(step)
        payload = {
            "name": name,
            "status": "passed" if step.passed else "failed",
            "statusDetails": self._build_status_details(
                step.error_message,
                getattr(step, "failure_type", None),
                diagnostics=diagnostics,
            ),
        }
        if parameters:
            payload["parameters"] = parameters
        return payload

    def _build_status_details(
        self,
        message: str | None,
        failure_type: str | None,
        diagnostics: dict | None = None,
    ) -> dict:
        payload: dict[str, object] = {"message": message or ""}
        if failure_type:
            payload["failureType"] = failure_type
        if diagnostics:
            payload["diagnostics"] = diagnostics
        return payload

    def _build_step_diagnostics(self, step) -> dict:
        diagnostics: dict[str, object] = {}
        if getattr(step, "duration_ms", None) is not None:
            diagnostics["duration_ms"] = step.duration_ms
        if getattr(step, "keyword_source", None) is not None:
            diagnostics["keyword_source"] = step.keyword_source
        diagnostics["dry_run"] = bool(getattr(step, "dry_run", False))
        if getattr(step, "arguments", None):
            diagnostics["arguments"] = step.arguments
        if getattr(step, "retry_attempt", None) is not None:
            diagnostics["retry_attempt"] = step.retry_attempt
        if getattr(step, "retry_max_retries", None) is not None:
            diagnostics["retry_max_retries"] = step.retry_max_retries
        if getattr(step, "case_attempt", None) is not None:
            diagnostics["case_attempt"] = step.case_attempt
        if getattr(step, "case_max_retries", None) is not None:
            diagnostics["case_max_retries"] = step.case_max_retries
        retry_trace = getattr(step, "retry_trace", None) or []
        if retry_trace:
            diagnostics["retry_trace"] = retry_trace
