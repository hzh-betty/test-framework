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
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    return cases


def read_failed_case_names(path: Path) -> set[str]:
    failed_names: set[str] = set()
    for case in read_case_results(path):
        if case.get("passed") is False and isinstance(case.get("name"), str):
            failed_names.add(case["name"])
    return failed_names
