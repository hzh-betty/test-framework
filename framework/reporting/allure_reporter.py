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
        name = f"{step.action} {step.target}"
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
        if getattr(step, "resolved_locator", None) is not None:
            diagnostics["resolved_locator"] = step.resolved_locator
        if getattr(step, "current_url", None) is not None:
            diagnostics["current_url"] = step.current_url
        return diagnostics

    def _build_step_parameters(self, step) -> list[dict[str, str]]:
        parameters: list[dict[str, str]] = []
        duration_ms = getattr(step, "duration_ms", None)
        if duration_ms is not None:
            parameters.append({"name": "duration_ms", "value": str(duration_ms)})
        retry_attempt = getattr(step, "retry_attempt", None)
        if retry_attempt is not None:
            parameters.append({"name": "retry_attempt", "value": str(retry_attempt)})
        retry_max_retries = getattr(step, "retry_max_retries", None)
        if retry_max_retries is not None:
            parameters.append({"name": "retry_max_retries", "value": str(retry_max_retries)})
        case_attempt = getattr(step, "case_attempt", None)
        if case_attempt is not None:
            parameters.append({"name": "case_attempt", "value": str(case_attempt)})
        case_max_retries = getattr(step, "case_max_retries", None)
        if case_max_retries is not None:
            parameters.append({"name": "case_max_retries", "value": str(case_max_retries)})
        locator = getattr(step, "resolved_locator", None)
        if isinstance(locator, dict):
            by = locator.get("by")
            value = locator.get("value")
            if isinstance(by, str):
                parameters.append({"name": "locator_by", "value": by})
            if isinstance(value, str):
                parameters.append({"name": "locator_value", "value": value})
        current_url = getattr(step, "current_url", None)
        if isinstance(current_url, str):
            parameters.append({"name": "current_url", "value": current_url})
        return parameters

    def _build_attachments(self, context, case_name, step_results) -> list[dict]:
        attachments: list[dict] = []
        if context is None:
            return attachments
        if context.runtime_log_path:
            attachments.append(
                self._write_attachment_file(
                    name="runtime.log",
                    content=self._read_or_placeholder(
                        context.runtime_log_path,
                        "runtime log not found",
                    ),
                    attachment_type="text/plain",
                    extension=".log",
                )
            )
        if context.dsl_path:
            attachments.append(
                self._write_attachment_file(
                    name="dsl-snippet.xml",
                    content=self._read_or_placeholder(
                        context.dsl_path,
                        "dsl file not found",
                    ),
                    attachment_type="text/plain",
                    extension=".xml",
                )
            )
        screenshot = self._find_failure_screenshot(case_name, step_results)
        if screenshot:
            attachments.append(
                self._write_attachment_file(
                    name="failure-screenshot.png",
                    content=Path(screenshot).read_bytes(),
                    attachment_type="image/png",
                    extension=".png",
                    binary=True,
                )
            )
        return attachments

    def _find_failure_screenshot(self, case_name: str, step_results) -> str | None:
        safe_case = case_name.strip().lower().replace(" ", "_")
        for step in step_results:
            if step.passed:
                continue
            safe_action = step.action.strip().lower().replace(" ", "_")
            screenshot = Path("artifacts/screenshots") / f"{safe_case}_{safe_action}.png"
            if screenshot.exists():
                return str(screenshot)
        return None

    def _read_or_placeholder(self, path: str, placeholder: str) -> str:
        file_path = Path(path)
        if file_path.exists():
            return file_path.read_text(encoding="utf-8", errors="replace")
        return placeholder

    def _write_attachment_file(
        self,
        name: str,
        content,
        attachment_type: str,
        extension: str,
        binary: bool = False,
    ) -> dict:
        source = f"{uuid4()}{extension}"
        target = self.results_dir / source
        if binary:
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        return {"name": name, "type": attachment_type, "source": source}

    def write_environment_properties(self, context: ReportContext) -> Path:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        env = self.results_dir / "environment.properties"
        env.write_text(
            "\n".join(
                [
                    f"browser={context.browser}",
                    f"headless={str(context.headless).lower()}",
                    f"python={context.python_version}",
                    f"version={context.framework_version}",
                ]
            ),
            encoding="utf-8",
        )
        return env

    def generate_html_report(self, output_dir: str | Path = "artifacts/allure-report") -> bool:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        command = [
            "allure",
            "generate",
            str(self.results_dir),
            "-o",
            str(output_path),
            "--clean",
        ]
        try:
            return self.command_runner(command) == 0
        except Exception:
            return False
