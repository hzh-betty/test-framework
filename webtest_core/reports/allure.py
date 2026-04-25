"""Allure 结果文件生成。

这里生成的是 Allure 可读取的 JSON artifact，不负责调用外部 allure CLI。
这样默认 HTML 报告和 Allure 输出互不依赖。
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from webtest_core.runtime import SuiteResult


def write_allure_results(
    output_dir: str | Path,
    result: SuiteResult,
    *,
    browser: str = "unknown",
    headless: bool = False,
    python_version: str = "unknown",
    framework_version: str = "unknown",
    runtime_log_path: str | None = None,
    dsl_path: str | None = None,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = output / "executor-summary.json"
    summary.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "environment.properties").write_text(
        "\n".join(
            [
                f"browser={browser}",
                f"headless={str(headless).lower()}",
                f"python={python_version}",
                f"version={framework_version}",
            ]
        ),
        encoding="utf-8",
    )
    for case in result.case_results:
        attachments = []
        if runtime_log_path:
            attachments.append({"name": "runtime.log", "source": runtime_log_path, "type": "text/plain"})
        if dsl_path:
            attachments.append({"name": "dsl-snippet.yaml", "source": dsl_path, "type": "text/yaml"})
        payload = {
            "uuid": str(uuid4()),
            "name": case.name,
            "status": "passed" if case.passed else "failed",
            "statusDetails": {
                "message": case.error_message,
                "failureType": case.failure_type,
            },
            "steps": [
                {
                    "name": step.keyword,
                    "status": "passed" if step.passed else "failed",
                    "statusDetails": {
                        "message": step.error_message,
                        "failureType": step.failure_type,
                        "diagnostics": {
                            "call_chain": step.call_chain,
                            "duration_ms": step.duration_ms,
                            "retry_attempt": step.retry_attempt,
                            "retry_max_retries": step.retry_max_retries,
                            "case_attempt": step.case_attempt,
                            "case_max_retries": step.case_max_retries,
                            "retry_trace": step.retry_trace,
                            "resolved_locator": step.resolved_locator,
                            "current_url": step.current_url,
                        },
                    },
                }
                for step in case.step_results
            ],
            "attachments": attachments,
        }
        (output / f"{uuid4()}-result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return output
