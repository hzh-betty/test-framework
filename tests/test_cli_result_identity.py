import json
from pathlib import Path

import yaml

import webtest_core.cli as cli
from webtest_core.keywords import KeywordRegistry
from webtest_core.reports import read_failed_case_names
from webtest_core.reports.case_results import read_case_results
from webtest_core.runtime.models import case_identity, suite_identity


def _latest(root):
    return Path(json.loads((root / "latest-run.json").read_text(encoding="utf-8"))["directory"])


def _allure_cases(directory):
    return [json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*-result.json")]


def _assert_allure_associations(run_directory, identities):
    output = run_directory / "allure-results"
    cases = _allure_cases(output)
    containers = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("*-container.json")]
    assert {case["testCaseId"] for case in cases} == identities
    assert len(cases) == len(identities)
    assert len({case["historyId"] for case in cases}) == len(identities)
    assert len(containers) == 1 and containers[0]["name"] == "***"
    assert len(containers[0]["children"]) == len(identities)
    assert set(containers[0]["children"]) == {case["uuid"] for case in cases}
    return {case["testCaseId"]: case for case in cases}


def test_cli_redacted_identities_survive_real_execution_rerun_and_merge(tmp_path, monkeypatch, capsys):
    suite_name = "PRIVATE_SUITE_PASSWORD"
    case_names = ["PRIVATE_FIRST_PASSWORD", "PRIVATE_SECOND_PASSWORD"]
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(yaml.safe_dump({"suite": {
        "name": suite_name,
        "variables": {"password": suite_name},
        "cases": [{"name": name, "steps": [{"keyword": "Input", "args": [name], "sensitive_args": [0]}]}
                  for name in case_names],
    }}), encoding="utf-8")
    calls = []
    fail_first = True

    def input_value(value):
        calls.append(value)
        if fail_first and value == case_names[0]:
            raise AssertionError(f"input rejected: {value}")

    def registry_factory():
        registry = KeywordRegistry()
        registry.register("Input", input_value)
        return registry

    monkeypatch.setattr(cli, "_build_registry", lambda args, config: registry_factory())
    output_root = tmp_path / "runs"
    flags = ["--html-report", "--allure", "--output-dir", str(output_root)]
    assert cli.main(["run", str(suite_file), *flags]) == 1
    assert calls == case_names
    first_directory = _latest(output_root)
    first_file = first_directory / "case-results.json"
    payload = json.loads(first_file.read_text(encoding="utf-8"))
    identities = {case_identity(suite_name, name) for name in case_names}
    assert payload["suite"] == "***" and payload["suite_id"] == suite_identity(suite_name)
    assert [case["name"] for case in payload["cases"]] == ["***", "***"]
    assert {case["case_id"] for case in payload["cases"]} == identities
    assert {case["suite_id"] for case in payload["cases"]} == {suite_identity(suite_name)}
    restored = read_case_results(first_file)
    assert restored.total_cases == 2 and restored.failed_cases == 1
    assert read_failed_case_names(first_file, suite_name=suite_name, case_names=case_names) == {case_names[0]}
    first_allure = _assert_allure_associations(first_directory, identities)
    assert first_allure[case_identity(suite_name, case_names[0])]["status"] == "failed"
    assert first_allure[case_identity(suite_name, case_names[1])]["status"] == "passed"

    calls.clear()
    fail_first = False
    assert cli.main(["run", str(suite_file), "--rerun-failed", str(first_file), *flags]) == 0
    assert calls == [case_names[0]]
    rerun_directory = _latest(output_root)
    rerun_file = rerun_directory / "case-results.json"
    rerun = read_case_results(rerun_file)
    assert rerun.total_cases == 1 and rerun.passed
    assert rerun.case_results[0].case_id == case_identity(suite_name, case_names[0])
    _assert_allure_associations(rerun_directory, {case_identity(suite_name, case_names[0])})

    calls.clear()
    assert cli.main(["run", "--merge-results", f"{first_file},{rerun_file}", *flags]) == 0
    assert calls == []
    merged_directory = _latest(output_root)
    merged_file = merged_directory / "case-results.json"
    merged = read_case_results(merged_file)
    assert merged.total_cases == merged.passed_cases == 2 and merged.passed
    assert {case.case_id for case in merged.case_results} == identities
    assert len(merged.suite_results) == 1 and merged.suite_results[0].suite_id == suite_identity(suite_name)
    assert read_failed_case_names(merged_file, suite_name=suite_name, case_names=case_names) == set()
    merged_allure = _assert_allure_associations(merged_directory, identities)
    assert all(case["status"] == "passed" for case in merged_allure.values())
    assert {identity: case["historyId"] for identity, case in first_allure.items()} == {
        identity: case["historyId"] for identity, case in merged_allure.items()}

    secrets = [suite_name, *case_names]
    for path in output_root.rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            assert all(secret not in content for secret in secrets), path
    captured = capsys.readouterr()
    assert all(secret not in captured.out + captured.err for secret in secrets)
