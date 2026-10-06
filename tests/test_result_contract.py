import json

import pytest

from webtest_core.dsl import DslValidationError
from webtest_core.reports import merge_case_results, read_failed_case_names, write_case_results
from webtest_core.reports.case_results import read_case_results
from webtest_core.runtime import CaseAttempt, CaseResult, StepResult, SuiteResult
from webtest_core.runtime.models import case_identity, identify_result, suite_identity


def _read_payload(tmp_path, case):
    source = tmp_path / "results.json"
    source.write_text(json.dumps({"suite": "A", "cases": [case]}), encoding="utf-8")
    return read_case_results(source)


@pytest.mark.parametrize("case", [
    {"name": "case", "passed": True, "steps": [{"keyword": "Fail", "passed": False}]},
    {"name": "case", "passed": True, "attempts": [{"attempt": 1, "passed": False}]},
    {"name": "case", "passed": False, "attempts": [{"attempt": 1, "passed": True}]},
    {"name": "case", "passed": True, "steps": [{"keyword": "Group", "passed": True,
        "children": [{"keyword": "Fail", "passed": False}]}]},
    {"name": "case", "passed": False, "attempts": [{"attempt": 1, "passed": True,
        "steps": [{"keyword": "Fail", "passed": False}]}]},
    {"name": "case", "passed": True, "steps": [{"keyword": "Pass", "passed": True}],
        "attempts": [{"attempt": 1, "passed": True, "steps": []}]},
    {"name": "case", "passed": True, "attempts": [{"attempt": 1, "passed": True},
        {"attempt": 2, "passed": True}]},
])
def test_result_contract_rejects_contradictory_final_status(tmp_path, case):
    with pytest.raises(DslValidationError):
        _read_payload(tmp_path, case)


@pytest.mark.parametrize("numbers", [[0], [-1], [True], ["1"], [2], [1, 1], [1, 3], [2, 1]])
def test_attempt_numbers_must_start_at_one_and_be_consecutive(tmp_path, numbers):
    case = {"name": "case", "passed": False,
        "attempts": [{"attempt": number, "passed": False} for number in numbers]}
    with pytest.raises(DslValidationError, match="attempt numbers"):
        _read_payload(tmp_path, case)


@pytest.mark.parametrize("field, value", [("retry_attempt", 0), ("case_attempt", -1), ("retry_attempt", True), ("case_attempt", "1")])
def test_step_attempt_numbers_must_be_positive_integers(tmp_path, field, value):
    with pytest.raises(DslValidationError, match="positive integer"):
        _read_payload(tmp_path, {"name": "case", "passed": True,
            "steps": [{"keyword": "Pass", "passed": True, field: value}]})


@pytest.mark.parametrize("case", [
    {"name": "case", "passed": True, "unexpected": 1},
    {"name": "case", "passed": True, "steps": [{"keyword": "Pass", "passed": True, "unexpected": 1}]},
    {"name": "case", "passed": True, "attempts": [{"attempt": 1, "passed": True, "unexpected": 1}]},
])
def test_result_contract_rejects_unknown_fields_at_each_level(tmp_path, case):
    with pytest.raises(DslValidationError, match="Unknown"):
        _read_payload(tmp_path, case)


def test_valid_retry_history_retains_failed_prior_attempt(tmp_path):
    first = StepResult("Fail", False, children=[StepResult("Child", False)])
    final = StepResult("Pass", True)
    case = CaseResult("case", True, [final], attempts=[
        CaseAttempt(1, False, [first], "first failed", "action"), CaseAttempt(2, True, [final])])
    original = SuiteResult("A", [case])
    source = write_case_results(tmp_path / "results.json", original)
    restored = read_case_results(source)
    assert restored.to_dict() == original.to_dict()
    assert restored.passed
    assert read_failed_case_names(source, suite_name="A") == set()


@pytest.mark.parametrize("passed, blocked", [(True, False), (False, False), (False, True)])
def test_empty_steps_allow_explicit_success_failure_and_blocked_cases(tmp_path, passed, blocked):
    result = _read_payload(tmp_path, {"name": "case", "passed": passed, "blocked": blocked})
    assert result.case_results[0].passed is passed
    assert result.case_results[0].blocked is blocked


def test_parent_run_failure_survives_remerge_and_affects_all_child_suites(tmp_path):
    original = SuiteResult("Combined", [CaseResult("one", True, suite="A"), CaseResult("two", True, suite="B")],
        error_message="deployment failed", failure_type="deploy", suite_results=[SuiteResult("A"), SuiteResult("B")])
    source = write_case_results(tmp_path / "original.json", original)
    assert not read_case_results(source).passed
    assert read_failed_case_names(source, suite_name="A") == {"one"}
    assert read_failed_case_names(source, suite_name="B") == {"two"}
    merged = merge_case_results([source])
    assert not merged.passed
    assert all(leaf.error_message == "Combined: deployment failed" for leaf in merged.suite_results)
    assert all(leaf.failure_type == "deploy" for leaf in merged.suite_results)
    saved = write_case_results(tmp_path / "merged.json", merged)
    remerged = merge_case_results([saved])
    assert remerged.to_dict() == merged.to_dict()
    rerun = write_case_results(tmp_path / "rerun.json", SuiteResult("A", [CaseResult("one", True)]))
    updated = write_case_results(tmp_path / "updated.json", merge_case_results([saved, rerun]))
    assert not read_case_results(updated).passed
    assert read_failed_case_names(updated, suite_name="A") == set()
    assert read_failed_case_names(updated, suite_name="B") == {"two"}


@pytest.mark.parametrize("phase", ["setup_steps", "teardown_steps"])
def test_parent_fixture_failure_survives_remerge(tmp_path, phase):
    original = SuiteResult("Combined", [CaseResult("case", True, suite="A")],
        suite_results=[SuiteResult("A")], **{phase: [StepResult("Fixture", False, error_message="fixture failed")]})
    source = write_case_results(tmp_path / "original.json", original)
    merged = merge_case_results([source])
    assert not merged.passed
    assert getattr(merged.suite_results[0], phase)[0].error_message == "fixture failed"
    saved = write_case_results(tmp_path / "merged.json", merged)
    assert read_failed_case_names(saved, suite_name="A") == {"case"}


def test_nested_case_results_survive_read_rerun_and_merge(tmp_path):
    original = SuiteResult("Combined", suite_results=[SuiteResult("A", [CaseResult("failed", False)]),
        SuiteResult("B", [CaseResult("passed", True)])])
    source = write_case_results(tmp_path / "original.json", original)
    assert read_case_results(source).to_dict() == original.to_dict()
    assert read_failed_case_names(source, suite_name="A") == {"failed"}
    assert read_failed_case_names(source, suite_name="B") == set()
    merged = merge_case_results([source])
    assert not merged.passed
    assert merged.total_cases == 2 and merged.failed_cases == 1
    assert {(case.suite, case.name) for case in merged.case_results} == {("A", "failed"), ("B", "passed")}


def test_duplicate_case_identity_across_nested_levels_is_rejected(tmp_path):
    original = SuiteResult("Combined", [CaseResult("case", True, suite="A")],
        suite_results=[SuiteResult("A", [CaseResult("case", True)])])
    source = write_case_results(tmp_path / "duplicate.json", original)
    with pytest.raises(DslValidationError, match="Duplicate case identities"):
        read_case_results(source)


def test_result_times_and_attachments_survive_round_trip_and_merge(tmp_path):
    step = StepResult("Screenshot", True, start=110, stop=120,
        attachments=[{"name": "screen", "path": "run/screenshots/screen.png", "type": "image/png"}])
    case = CaseResult("case", True, [step], attempts=[CaseAttempt(1, True, [step], start=105, stop=130)],
        start=105, stop=130)
    original = SuiteResult("A", [case], start=100, stop=140)
    source = write_case_results(tmp_path / "timed.json", original)
    assert read_case_results(source).to_dict() == original.to_dict()
    merged = merge_case_results([source])
    assert merged.suite_results[0].start == 100 and merged.suite_results[0].stop == 140
    assert merged.case_results[0].step_results[0].attachments == step.attachments
    saved = write_case_results(tmp_path / "merged-timed.json", merged)
    assert read_case_results(saved).to_dict() == merged.to_dict()


@pytest.mark.parametrize("level", ["suite", "case", "attempt", "step"])
@pytest.mark.parametrize("timing", [
    {"start": -1}, {"stop": -1}, {"start": True}, {"stop": False},
    {"start": "100"}, {"stop": 100.0}, {"start": 100, "stop": 99},
])
def test_invalid_result_times_are_rejected_at_every_level(tmp_path, level, timing):
    step = {"keyword": "Pass", "passed": True}
    attempt = {"attempt": 1, "passed": True, "steps": [step]}
    case = {"name": "case", "passed": True, "steps": [step], "attempts": [attempt]}
    payload = {"suite": "A", "cases": [case]}
    {"suite": payload, "case": case, "attempt": attempt, "step": step}[level].update(timing)
    source = tmp_path / "invalid-time.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DslValidationError, match=rf"{level}\.(start|stop)"):
        read_case_results(source)


@pytest.mark.parametrize("timing", [{"start": None, "stop": None}, {"start": 0}, {"stop": 0}, {"start": 0, "stop": 0}])
def test_result_times_allow_missing_endpoints_and_zero(tmp_path, timing):
    step = {"keyword": "Pass", "passed": True, **timing}
    case = {"name": "case", "passed": True, "steps": [step],
        "attempts": [{"attempt": 1, "passed": True, "steps": [step], **timing}], **timing}
    source = tmp_path / "valid-time.json"
    source.write_text(json.dumps({"suite": "A", "cases": [case], **timing}), encoding="utf-8")
    restored = read_case_results(source)
    assert restored.start == timing.get("start")
    assert restored.stop == timing.get("stop")
    assert restored.passed


def test_secret_case_and_suite_names_keep_distinct_rerun_and_merge_identities(tmp_path):
    suite_name, first_name, second_name = "PRIVATE_SUITE", "PRIVATE_A", "PRIVATE_B"
    secrets = [suite_name, first_name, second_name]
    first = CaseResult(first_name, False, [StepResult("Input", False, kwargs={"password": secrets})])
    second = CaseResult(second_name, True)
    original = SuiteResult(suite_name, [first, second])
    source = write_case_results(tmp_path / "secret-names.json", original)
    contents = source.read_text(encoding="utf-8")
    assert all(secret not in contents for secret in secrets)
    payload = json.loads(contents)
    assert payload["suite"] == "***"
    assert [case["name"] for case in payload["cases"]] == ["***", "***"]
    assert payload["suite_id"] == suite_identity(suite_name)
    assert {case["case_id"] for case in payload["cases"]} == {
        case_identity(suite_name, first_name), case_identity(suite_name, second_name)}
    restored = read_case_results(source)
    assert restored.total_cases == 2 and restored.failed_cases == 1
    assert read_failed_case_names(source, suite_name=suite_name, case_names=[first_name, second_name]) == {first_name}
    with pytest.raises(DslValidationError, match="require current case_names"):
        read_failed_case_names(source, suite_name=suite_name)
    saved = write_case_results(tmp_path / "secret-merged.json", merge_case_results([source]))
    assert read_case_results(saved).total_cases == 2
    assert read_failed_case_names(saved, suite_name=suite_name, case_names=[first_name, second_name]) == {first_name}
    rerun = write_case_results(tmp_path / "rerun-secret.json", SuiteResult(suite_name, [CaseResult(first_name, True,
        [StepResult("Input", True, kwargs={"password": secrets})])]))
    updated = write_case_results(tmp_path / "updated-secret.json", merge_case_results([saved, rerun]))
    assert read_case_results(updated).passed and read_case_results(updated).total_cases == 2
    assert read_failed_case_names(updated, suite_name=suite_name, case_names=[first_name, second_name]) == set()
    assert all(secret not in updated.read_text(encoding="utf-8") for secret in secrets)
    assert original.suite_id is None and first.case_id is None
    assert original.name == suite_name and first.name == first_name


def test_distinct_suites_with_same_redacted_display_name_do_not_merge(tmp_path):
    paths = []
    for index, suite_name in enumerate(["PRIVATE_SUITE_A", "PRIVATE_SUITE_B"]):
        passed = index == 1
        original = SuiteResult(suite_name, [CaseResult("case", passed,
            [StepResult("Input", passed, kwargs={"password": suite_name})])])
        paths.append(write_case_results(tmp_path / f"suite-{index}.json", original))
    merged = merge_case_results(paths)
    assert merged.total_cases == 2 and len(merged.suite_results) == 2
    assert [leaf.name for leaf in merged.suite_results] == ["***", "***"]
    saved = write_case_results(tmp_path / "merged-suites.json", merged)
    assert read_case_results(saved).failed_cases == 1
    assert read_failed_case_names(saved, suite_name="PRIVATE_SUITE_A") == {"case"}
    assert read_failed_case_names(saved, suite_name="PRIVATE_SUITE_B") == set()
    assert "PRIVATE_SUITE" not in saved.read_text(encoding="utf-8")


def test_parent_failure_reruns_every_child_after_identity_names_are_redacted(tmp_path):
    suite_names = ["PRIVATE_SUITE_A", "PRIVATE_SUITE_B"]
    case_names = ["PRIVATE_A", "PRIVATE_B"]
    original = SuiteResult("Combined", suite_results=[SuiteResult(suite_name, [CaseResult(case_name, True)])
        for suite_name, case_name in zip(suite_names, case_names)], error_message="run failed",
        setup_steps=[StepResult("Input", True, kwargs={"password": suite_names + case_names})])
    source = write_case_results(tmp_path / "parent-secret.json", original)
    saved = write_case_results(tmp_path / "parent-secret-merged.json", merge_case_results([source]))
    assert not read_case_results(saved).passed
    for suite_name, case_name in zip(suite_names, case_names):
        assert read_failed_case_names(saved, suite_name=suite_name, case_names=[case_name]) == {case_name}
    assert all(secret not in saved.read_text(encoding="utf-8") for secret in suite_names + case_names)


@pytest.mark.parametrize("value", ["a" * 63, "A" * 64, "g" * 64, 1, True, "sha256:" + "a" * 64])
@pytest.mark.parametrize("level, field", [("suite", "suite_id"), ("case", "suite_id"), ("case", "case_id")])
def test_invalid_opaque_result_identities_are_rejected(tmp_path, value, level, field):
    case = {"name": "case", "passed": False}
    payload = {"suite": "A", "cases": [case]}
    (payload if level == "suite" else case)[field] = value
    source = tmp_path / "bad-identity.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DslValidationError, match="lowercase SHA-256 identity"):
        read_case_results(source)


def test_case_cannot_claim_another_suite_identity(tmp_path):
    with pytest.raises(DslValidationError, match="suite identity does not match"):
        _read_payload(tmp_path, {"name": "case", "passed": False, "suite_id": suite_identity("B")})


def test_case_identity_collision_is_rejected_even_with_distinct_display_names(tmp_path):
    payload = {"suite": "A", "cases": [
        {"name": "first", "passed": False, "case_id": case_identity("A", "first")},
        {"name": "second", "passed": False, "case_id": case_identity("A", "first")}]}
    source = tmp_path / "collision.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DslValidationError, match="Duplicate case identities"):
        read_case_results(source)


def test_current_case_mapping_reports_unresolvable_failed_identity(tmp_path):
    source = write_case_results(tmp_path / "missing-current-case.json", SuiteResult("A", [CaseResult("old", False,
        [StepResult("Input", False, kwargs={"password": "old"})])]))
    with pytest.raises(DslValidationError, match="Cannot resolve failed case identity"):
        read_failed_case_names(source, suite_name="A", case_names=["new"])


def test_current_case_mapping_keeps_plain_historical_names_for_existing_filters(tmp_path):
    source = write_case_results(tmp_path / "historical-case.json", SuiteResult("A", [CaseResult("old", False)]))
    assert read_failed_case_names(source, suite_name="A", case_names=["new"]) == {"old"}


def test_literal_redaction_marker_in_original_case_name_remains_resolvable(tmp_path):
    source = write_case_results(tmp_path / "literal-name.json", SuiteResult("A", [CaseResult("literal ***", False)]))
    assert read_failed_case_names(source, suite_name="A") == {"literal ***"}


def test_identity_assignment_uses_explicit_child_suite_ids_without_mutating_models():
    identity = suite_identity("original")
    original = SuiteResult("Combined", [CaseResult("case", True, suite="display")],
        suite_results=[SuiteResult("display", suite_id=identity)])
    identified = identify_result(original)
    assert identified.case_results[0].suite_id == identity
    assert identified.suite_results[0].suite_id == identity
    assert original.case_results[0].suite_id is None and original.suite_id is None
