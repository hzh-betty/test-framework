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

    def write_suite_result(self, result: SuiteExecutionResult) -> Path:
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
            }
            case_file = self.results_dir / f"{case_payload['uuid']}-result.json"
            case_file.write_text(
                json.dumps(case_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return summary_file

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
