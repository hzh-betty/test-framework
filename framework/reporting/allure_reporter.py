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
                "statusDetails": {"message": case.error_message or ""},
                "labels": [
                    {"name": "suite", "value": result.name},
                    {"name": "framework", "value": "custom-webtest-framework"},
                ],
                "steps": steps,
                "attachments": attachments,
            }
            case_file = self.results_dir / f"{case_payload['uuid']}-result.json"
            case_file.write_text(
                json.dumps(case_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return summary_file

    def _build_step_payload(self, step) -> dict:
        return {
            "name": f"{step.action} {step.target}",
            "status": "passed" if step.passed else "failed",
            "statusDetails": {"message": step.error_message or ""},
        }

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
