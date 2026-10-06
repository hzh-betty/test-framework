"""Allure 文件与附件全部位于独立、可复制的 results 目录。"""

import hashlib
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import yaml

from webtest_core.redaction import Redactor
from webtest_core.reports.io import write_json
from webtest_core.runtime import SuiteResult


def _status(passed, failure_type=None, blocked=False):
    if blocked:
        return "skipped"
    return "passed" if passed else ("failed" if failure_type == "assertion" else "broken")


def _step(step):
    return {"name": step.keyword, "status": _status(step.passed, step.failure_type),
            "statusDetails": {"message": step.error_message}, "steps": [_step(child) for child in step.children]}


def write_allure_results(output_dir: str | Path, result: SuiteResult, *, browser="unknown", headless=False,
                        python_version="unknown", framework_version="unknown", runtime_log_path=None,
                        dsl_path=None, redactor: Redactor | None = None) -> Path:
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Allure output must be a new empty directory")
    output.mkdir(parents=True, exist_ok=True)
    redactor = redactor or Redactor(asdict(result))
    (output / "environment.properties").write_text(
        f"browser={browser}\nheadless={str(headless).lower()}\npython={python_version}\nversion={framework_version}\n", encoding="utf-8")
    attachments = []
    if dsl_path and Path(dsl_path).is_file():
        payload = yaml.safe_load(Path(dsl_path).read_text(encoding="utf-8"))
        redactor.collect(payload)
        name = f"{uuid4()}-attachment.yaml"
        (output / name).write_text(yaml.safe_dump(redactor.redact(payload), allow_unicode=True), encoding="utf-8")
        attachments.append({"name": "dsl.yaml", "source": name, "type": "text/yaml"})
    if runtime_log_path and Path(runtime_log_path).is_file():
        name = f"{uuid4()}-attachment.log"
        (output / name).write_text(redactor.redact(Path(runtime_log_path).read_text(encoding="utf-8")), encoding="utf-8")
        attachments.append({"name": "runtime.log", "source": name, "type": "text/plain"})
    write_json(output / "executor-summary.json", redactor.redact(result.to_dict()))
    case_ids = {}
    for case in result.case_results:
        identifier = str(uuid4())
        suite_name = case.suite or result.name
        case_ids.setdefault(suite_name, []).append(identifier)
        identity = f"{suite_name}::{case.name}"
        history_id = hashlib.sha256(f"{identity}::{browser}::{headless}".encode()).hexdigest()
        diagnostics = f"{uuid4()}-attachment.json"
        write_json(output / diagnostics, redactor.redact(case.to_dict()))
        payload = {"uuid": identifier, "name": case.name, "fullName": identity, "historyId": history_id,
            "testCaseId": hashlib.sha256(identity.encode()).hexdigest(),
            "status": _status(case.passed, case.failure_type, case.blocked),
            "statusDetails": {"message": redactor.redact(case.error_message)},
            "steps": [_step(step) for step in case.step_results],
            "labels": [{"name": "suite", "value": suite_name}, *[{"name": "tag", "value": tag} for tag in case.tags]],
            "attachments": [*attachments, {"name": "diagnostics.json", "source": diagnostics, "type": "application/json"}]}
        write_json(output / f"{identifier}-result.json", redactor.redact(payload))
    lifecycles = result.suite_results or [result]
    for lifecycle in lifecycles:
        write_json(output / f"{uuid4()}-container.json", redactor.redact({"uuid": str(uuid4()), "name": lifecycle.name,
            "children": case_ids.get(lifecycle.name, []),
            "befores": [{"name": "Suite setup", "status": _status(not lifecycle.suite_setup_failed),
                          "steps": [_step(step) for step in lifecycle.setup_steps]}],
            "afters": [{"name": "Suite teardown", "status": _status(not lifecycle.suite_teardown_failed),
                         "steps": [_step(step) for step in lifecycle.teardown_steps]}]}))
        if lifecycle.error_message or (not case_ids.get(lifecycle.name) and not lifecycle.passed):
            identifier = str(uuid4())
            write_json(output / f"{identifier}-result.json", redactor.redact({"uuid": identifier, "name": f"{lifecycle.name}::run failure",
                "status": "broken", "statusDetails": {"message": lifecycle.error_message},
                "steps": [_step(step) for step in lifecycle.setup_steps + lifecycle.teardown_steps], "attachments": attachments}))
    return output
