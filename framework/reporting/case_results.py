from __future__ import annotations

import json
from pathlib import Path


def write_case_results(path: Path, cases: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cases": cases}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def read_case_results(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("case-results payload must be a JSON object")
    if "cases" not in payload:
        raise ValueError('case-results payload is missing required "cases" key')
    cases = payload["cases"]
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case item at index {index} must be an object")
    return cases


def read_failed_case_names(path: Path) -> set[str]:
    failed_names: set[str] = set()
    for index, case in enumerate(read_case_results(path)):
        if "name" not in case:
            raise ValueError(f"case item at index {index} is missing required string 'name'")
        if not isinstance(case["name"], str):
            raise ValueError(f"case item at index {index} must have string 'name'")
        if "passed" not in case:
            raise ValueError(f"case item at index {index} is missing required bool 'passed'")
        if not isinstance(case["passed"], bool):
            raise ValueError(f"case item at index {index} must have bool 'passed'")
        if case["passed"] is False:
            failed_names.add(case["name"])
    return failed_names
