"""Allure 文件与附件全部位于独立、可复制的 results 目录。"""

import hashlib
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import yaml

from webtest_core.redaction import Redactor
from webtest_core.reports.attachments import copy_screenshots
from webtest_core.reports.case_results import _all_cases, _lifecycles
from webtest_core.reports.io import write_json
from webtest_core.runtime import SuiteResult


def _status(passed, failure_type=None, blocked=False):
    if blocked:
        return "skipped"
    return "passed" if passed else ("failed" if failure_type == "assertion" else "broken")


def _step(step):
    return {"name": step.keyword, "status": _status(step.passed, step.failure_type),
            "statusDetails": {"message": step.error_message}, "steps": [_step(child) for child in step.children],
            "attachments": step.attachments,
            **_timing(step)}


def _timing(result):
    return {name: value for name in ("start", "stop") if (value := getattr(result, name, None)) is not None}


def write_allure_results(output_dir: str | Path, result: SuiteResult, *, browser="unknown", headless=False,
                        python_version="unknown", framework_version="unknown", runtime_log_path=None,
                        dsl_path=None, redactor: Redactor | None = None) -> Path:
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Allure output must be a new empty directory")
    output.mkdir(parents=True, exist_ok=True)
    redactor = redactor or Redactor()
    redactor.collect(asdict(result))
    attachments = []
    if dsl_path and Path(dsl_path).is_file():
        payload = yaml.safe_load(Path(dsl_path).read_text(encoding="utf-8"))
        redactor.collect_suite(payload)
        name = f"{uuid4()}-attachment.yaml"
        (output / name).write_text(yaml.safe_dump(redactor.redact_suite(payload), allow_unicode=True), encoding="utf-8")
        attachments.append({"name": "dsl.yaml", "source": name, "type": "text/yaml"})
    if runtime_log_path and Path(runtime_log_path).is_file():
        name = f"{uuid4()}-attachment.log"
        (output / name).write_text(redactor.redact(Path(runtime_log_path).read_text(encoding="utf-8")), encoding="utf-8")
        attachments.append({"name": "runtime.log", "source": name, "type": "text/plain"})
    safe_result = redactor.redact_result(result)
    copy_screenshots(result, safe_result, output)
    result = safe_result
    (output / "environment.properties").write_text(
        f"browser={redactor.redact(browser)}\nheadless={str(headless).lower()}\npython={redactor.redact(python_version)}\nversion={redactor.redact(framework_version)}\n", encoding="utf-8")
    write_json(output / "executor-summary.json", result.to_dict())
    case_ids = {}
    seen = set()
    for case in _all_cases(result):
        key = (case.suite_id, case.case_id)
        if key in seen:
            continue
        seen.add(key)
        identifier = str(uuid4())
        suite_name = case.suite or result.name
        case_ids.setdefault(case.suite_id, []).append(identifier)
        identity = f"{suite_name}::{case.name}"
        history_id = hashlib.sha256(f"{case.case_id}::{browser}::{headless}".encode()).hexdigest()
        diagnostics = f"{uuid4()}-attachment.json"
        write_json(output / diagnostics, case.to_dict())
        payload = {"uuid": identifier, "name": case.name, "fullName": identity, "historyId": history_id,
            "testCaseId": case.case_id,
            "status": _status(case.passed, case.failure_type, case.blocked),
            "statusDetails": {"message": case.error_message},
            "steps": [_step(step) for step in case.step_results],
            "labels": [{"name": "suite", "value": suite_name}, *[{"name": "tag", "value": tag} for tag in case.tags]],
            "attachments": [*attachments, {"name": "diagnostics.json", "source": diagnostics, "type": "application/json"}],
            **_timing(case)}
        write_json(output / f"{identifier}-result.json", payload)
    lifecycles = _lifecycles(result)
    for lifecycle in lifecycles:
        children = case_ids.get(lifecycle.suite_id, [])
        write_json(output / f"{uuid4()}-container.json", {"uuid": str(uuid4()), "name": lifecycle.name,
            "children": children,
            "befores": [{"name": "Suite setup", "status": _status(not lifecycle.suite_setup_failed),
                          "steps": [_step(step) for step in lifecycle.setup_steps]}],
            "afters": [{"name": "Suite teardown", "status": _status(not lifecycle.suite_teardown_failed),
                         "steps": [_step(step) for step in lifecycle.teardown_steps]}], **_timing(lifecycle)})
        if lifecycle.error_message or lifecycle.suite_setup_failed or lifecycle.suite_teardown_failed or (not children and not lifecycle.passed):
            identifier = str(uuid4())
            message = lifecycle.error_message or next((step.error_message for step in lifecycle.setup_steps + lifecycle.teardown_steps if not step.passed), None)
            write_json(output / f"{identifier}-result.json", {"uuid": identifier, "name": f"{lifecycle.name}::run failure",
                "status": "broken", "statusDetails": {"message": message},
                "steps": [_step(step) for step in lifecycle.setup_steps + lifecycle.teardown_steps], "attachments": attachments,
                **_timing(lifecycle)})
    return output
