from pathlib import Path

import pytest

from framework.reporting.case_results import (
    read_case_results,
    read_failed_case_names,
    write_case_results,
)


def test_case_results_roundtrip(tmp_path: Path):
    cases = [
        {"name": "Login", "passed": False, "error_message": "mismatch"},
        {"name": "Profile", "passed": True},
    ]
    output = tmp_path / "nested" / "case-results.json"

    written = write_case_results(output, cases)

    assert written == output
    assert read_case_results(output) == cases


def test_read_failed_case_names(tmp_path: Path):
    path = tmp_path / "case-results.json"
    write_case_results(
        path,
        [
            {"name": "Login", "passed": False},
            {"name": "Checkout", "passed": True},
            {"name": "Search", "passed": False},
        ],
    )

    assert read_failed_case_names(path) == {"Login", "Search"}


def test_read_case_results_rejects_non_object_payload(tmp_path: Path):
    path = tmp_path / "case-results.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a JSON object"):
        read_case_results(path)


def test_read_case_results_rejects_non_list_cases(tmp_path: Path):
    path = tmp_path / "case-results.json"
    path.write_text('{"cases": {"name": "Login"}}', encoding="utf-8")

    with pytest.raises(ValueError, match="cases must be a list"):
        read_case_results(path)


def test_read_failed_case_names_rejects_missing_cases_key(tmp_path: Path):
    path = tmp_path / "case-results.json"
    path.write_text('{"foo": []}', encoding="utf-8")

    with pytest.raises(ValueError, match='missing required "cases" key'):
        read_failed_case_names(path)


def test_read_failed_case_names_rejects_non_object_case_items(tmp_path: Path):
    path = tmp_path / "case-results.json"
    path.write_text('{"cases": ["bad"]}', encoding="utf-8")

    with pytest.raises(ValueError, match="case item at index 0 must be an object"):
        read_failed_case_names(path)
