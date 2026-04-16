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


def test_build_suite_result_from_merged_cases_rejects_non_bool_step_passed():
    with pytest.raises(ValueError, match='step "passed" must be a bool'):
        build_suite_result_from_merged_cases(
            [
                {
                    "name": "Login",
                    "passed": True,
                    "step_results": [{"action": "click", "target": "#submit", "passed": 1}],
                }
            ]
        )


def test_build_suite_result_from_merged_cases_preserves_failure_type_fields():
    suite_result = build_suite_result_from_merged_cases(
        [
            {
                "name": "Login",
                "passed": False,
                "error_message": "timed out",
                "failure_type": "timeout",
                "step_results": [
                    {
                        "action": "wait_visible",
                        "target": "id=spinner",
                        "passed": False,
                        "error_message": "timed out",
                        "failure_type": "timeout",
                        "duration_ms": 321,
                        "retry_attempt": 2,
                        "retry_max_retries": 3,
                        "case_attempt": 1,
                        "case_max_retries": 1,
                        "retry_trace": [
                            {"attempt": 1, "status": "failed", "error": "timed out"},
                            {"attempt": 2, "status": "failed", "error": "timed out again"},
                        ],
                        "resolved_locator": {
                            "raw": "id=spinner",
                            "by": "id",
                            "value": "spinner",
                        },
                        "current_url": "https://example.test/login",
                    }
                ],
            }
        ]
    )

    case = suite_result.case_results[0]
    assert case.failure_type == "timeout"
    assert case.step_results[0].failure_type == "timeout"
    assert case.step_results[0].duration_ms == 321
    assert case.step_results[0].retry_attempt == 2
    assert case.step_results[0].retry_max_retries == 3
    assert case.step_results[0].case_attempt == 1
    assert case.step_results[0].case_max_retries == 1
    assert case.step_results[0].retry_trace == [
        {"attempt": 1, "status": "failed", "error": "timed out"},
        {"attempt": 2, "status": "failed", "error": "timed out again"},
    ]
    assert case.step_results[0].resolved_locator == {
        "raw": "id=spinner",
        "by": "id",
        "value": "spinner",
    }
    assert case.step_results[0].current_url == "https://example.test/login"


def test_build_suite_result_from_merged_cases_accepts_legacy_step_payload_without_observability():
    suite_result = build_suite_result_from_merged_cases(
        [
            {
                "name": "LegacyCase",
                "passed": True,
                "step_results": [{"action": "click", "target": "id=submit", "passed": True}],
            }
        ]
    )

    step = suite_result.case_results[0].step_results[0]
    assert step.duration_ms is None
    assert step.retry_attempt is None
    assert step.retry_max_retries is None
    assert step.case_attempt is None
    assert step.case_max_retries is None
    assert step.retry_trace == []
    assert step.resolved_locator is None
    assert step.current_url is None


def test_load_merged_suite_result_marks_suite_failure_when_any_source_teardown_failed(
    tmp_path: Path,
):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_case_results(first, [{"name": "Login", "passed": True}])
    write_case_results(
        second,
        [{"name": "Search", "passed": True}],
        suite_teardown_failed=True,
        suite_teardown_error_message="Suite teardown failed: timeout",
        suite_teardown_failure_type="timeout",
    )

    result = load_merged_suite_result([first, second], suite_name="MergedSuite")

    assert result.name == "MergedSuite"
    assert result.failed_cases == 0
    assert result.suite_teardown_failed is True
    assert result.suite_teardown_error_message == "Suite teardown failed: timeout"
    assert result.suite_teardown_failure_type == "timeout"


def test_load_merged_suite_result_accepts_legacy_payload_with_only_cases(tmp_path: Path):
    legacy_payload = tmp_path / "legacy.json"
    legacy_payload.write_text(
        '{"cases": [{"name": "LegacyCase", "passed": true}]}',
        encoding="utf-8",
    )

    result = load_merged_suite_result([legacy_payload])

    assert result.total_cases == 1
    assert result.suite_teardown_failed is False
    assert result.suite_teardown_error_message is None
    assert result.suite_teardown_failure_type is None


@pytest.mark.parametrize(
    "field_name",
    [
        "duration_ms",
        "retry_attempt",
        "retry_max_retries",
        "case_attempt",
        "case_max_retries",
    ],
)
def test_build_suite_result_from_merged_cases_rejects_bool_for_int_observability_fields(
    field_name: str,
):
    with pytest.raises(ValueError, match=field_name):
        build_suite_result_from_merged_cases(
            [
                {
                    "name": "Login",
                    "passed": True,
                    "step_results": [
                        {
                            "action": "click",
                            "target": "id=submit",
                            "passed": True,
                            field_name: True,
                        }
                    ],
                }
            ]
        )


def test_build_suite_result_from_merged_cases_rejects_bool_retry_trace_attempt():
    with pytest.raises(ValueError, match='retry_trace.attempt'):
        build_suite_result_from_merged_cases(
            [
                {
                    "name": "Login",
                    "passed": True,
                    "step_results": [
                        {
                            "action": "click",
                            "target": "id=submit",
                            "passed": True,
                            "retry_trace": [{"attempt": True, "status": "failed"}],
                        }
                    ],
                }
            ]
        )
