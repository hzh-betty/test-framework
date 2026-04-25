from pathlib import Path

import pytest

from framework.executor.models import SuiteExecutionResult
from framework.reporting.case_results import write_case_results
from framework.reporting.result_merge import (
    build_suite_result_from_merged_cases,
    load_merged_suite_result,
    merge_case_results,
    parse_merge_results_argument,
    read_and_merge_case_results,
)


def test_merge_case_results_overwrites_by_case_name():
    merged = merge_case_results(
        [{"name": "Login", "passed": False}, {"name": "Search", "passed": True}],
        [{"name": "Login", "passed": True, "error_message": None}],
    )

    assert list(merged.keys()) == ["Login", "Search"]
    assert merged["Login"]["passed"] is True
    assert merged["Search"]["passed"] is True


def test_merge_case_results_rejects_case_without_name():
    with pytest.raises(ValueError, match="must include a string name"):
        merge_case_results([{"passed": True}])


def test_merge_case_results_rejects_non_object_case():
    with pytest.raises(ValueError, match="must be an object"):
        merge_case_results(["bad"])  # type: ignore[list-item]


def test_parse_merge_results_argument_rejects_empty_items():
    with pytest.raises(ValueError, match="contains empty file entry"):
        parse_merge_results_argument("a.json, ,b.json")


def test_read_and_merge_case_results(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_case_results(first, [{"name": "Login", "passed": False}])
    write_case_results(second, [{"name": "Login", "passed": True}, {"name": "Pay", "passed": True}])

    merged = read_and_merge_case_results([first, second])

    assert merged == [{"name": "Login", "passed": True}, {"name": "Pay", "passed": True}]


def test_build_suite_result_from_merged_cases_counts_pass_and_fail():
    suite_result = build_suite_result_from_merged_cases(
        [{"name": "Login", "passed": True}, {"name": "Checkout", "passed": False}],
        suite_name="MergedSuite",
    )

    assert isinstance(suite_result, SuiteExecutionResult)
    assert suite_result.name == "MergedSuite"
    assert suite_result.total_cases == 2
    assert suite_result.passed_cases == 1
    assert suite_result.failed_cases == 1
    assert [case.name for case in suite_result.case_results] == ["Login", "Checkout"]


def test_build_suite_result_from_merged_cases_rejects_non_bool_case_passed():
    with pytest.raises(ValueError, match='case "passed" must be a bool'):
        build_suite_result_from_merged_cases([{"name": "Login", "passed": "true"}])

