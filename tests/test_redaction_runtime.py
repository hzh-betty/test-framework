import json
from unittest.mock import patch

import pytest

from webtest_core.dsl import CaseSpec, DslValidationError, StepSpec, SuiteSpec
from webtest_core.keywords import KeywordRegistry
from webtest_core.redaction import Redactor
from webtest_core.reports.case_results import read_case_results, write_case_results
from webtest_core.runtime import SuiteExecutor
import webtest_core.runtime.executor as executor_module


@pytest.mark.parametrize("default", [False, True])
def test_preflight_redacts_sensitive_bound_parameters_before_validation(default):
    secret = "PRIVATE_BOUND_PASSWORD"
    redactor = Redactor()
    called = []

    def factory():
        registry = KeywordRegistry()

        def action(password=secret):
            called.append(password)

        def validate(name, arguments):
            raise ValueError(f"rejected {arguments['password']}")

        registry.register("Login", action, validator=validate)
        return registry

    step = StepSpec(keyword="Login", args=[] if default else ["${cred}"])
    suite = SuiteSpec(name="Preflight", variables={"cred": secret}, cases=[CaseSpec(name="one", steps=[step])])
    executor = SuiteExecutor(factory, redactor=redactor)
    with pytest.raises(DslValidationError) as error:
        executor.validate_suite(suite)
    assert secret not in str(error.value)
    result = executor.run_suite(suite)
    assert secret not in json.dumps(result.to_dict())
    assert secret in redactor.secrets
    assert called == []


def test_preflight_cleanup_error_uses_collected_secret():
    secret = "PRIVATE_CLEANUP_PASSWORD"
    redactor = Redactor()

    def factory():
        def cleanup():
            raise RuntimeError(f"cleanup rejected {secret}")
        registry = KeywordRegistry(cleanup=cleanup)
        registry.register("Login", lambda value: None)
        return registry

    suite = SuiteSpec(name="Cleanup", variables={"cred": secret}, cases=[CaseSpec(name="one", steps=[
        StepSpec(keyword="Login", args=["${cred}"], sensitive_args=[0])])])
    executor = SuiteExecutor(factory, redactor=redactor)
    with pytest.raises(RuntimeError) as error:
        executor.validate_suite(suite)
    assert secret not in str(error.value)
    assert secret in redactor.secrets


def test_preflight_redacts_default_password_input_text_before_validator():
    secret = "PRIVATE_DEFAULT_TEXT"
    def factory():
        registry = KeywordRegistry()
        def action(locator="id=password", text=secret):
            pytest.fail("invalid action executed")
        def validate(name, arguments):
            raise ValueError("rejected " + arguments["text"])
        registry.register("Type Text", action, validator=validate)
        return registry
    suite = SuiteSpec(name="Default", cases=[CaseSpec(name="case", steps=[StepSpec(keyword="TYPE__TEXT")])])
    result = SuiteExecutor(factory).run_suite(suite)
    assert not result.passed
    assert secret not in json.dumps(result.to_dict())
    assert "***" in result.error_message


@pytest.mark.parametrize("value", [0, 1, 123456, {"pin": 123456}, [123456]])
def test_sensitive_arguments_are_masked_without_changing_action_or_statistics(value, tmp_path):
    received = []

    def factory():
        registry = KeywordRegistry()
        registry.register("Input", lambda credential: received.append(credential))
        return registry

    suite = SuiteSpec(name="Numeric", cases=[CaseSpec(name="case", steps=[
        StepSpec(keyword="Input", args=[value], sensitive_args=[0])])])
    executor = SuiteExecutor(factory)
    result = executor.run_suite(suite)
    assert received == [value]
    assert result.case_results[0].step_results[0].arguments == ["***"]
    payload = json.loads(write_case_results(tmp_path / "result.json", result, redactor=executor.redactor).read_text())
    assert payload["passed"] is True and payload["passed_cases"] == 1 and payload["failed_cases"] == 0
    assert payload["cases"][0]["steps"][0]["arguments"] == ["***"]


def test_secret_matching_failure_type_does_not_break_result_contract(tmp_path):
    def factory():
        registry = KeywordRegistry()
        def action(value):
            raise RuntimeError(f"rejected {value}")
        registry.register("Input", action)
        return registry

    suite = SuiteSpec(name="Enums", cases=[CaseSpec(name="case", steps=[
        StepSpec(keyword="Input", args=["action"], sensitive_args=[0])])])
    executor = SuiteExecutor(factory)
    result = executor.run_suite(suite)
    restored = read_case_results(write_case_results(tmp_path / "result.json", result, redactor=executor.redactor))
    assert restored.failure_type is None
    assert restored.case_results[0].failure_type == "action"
    assert restored.case_results[0].error_message == "rejected ***"


def test_initial_suite_is_scanned_once_and_contexts_remain_independent():
    suite = SuiteSpec(name="Scale", cases=[CaseSpec(name=str(index)) for index in range(100)])
    original_dump = SuiteSpec.model_dump
    with patch.object(SuiteSpec, "model_dump", autospec=True, side_effect=original_dump) as dump:
        result = SuiteExecutor(KeywordRegistry, dry_run=True).run_suite(suite)
    assert result.passed and result.total_cases == 100
    assert dump.call_count == 1


def test_shared_unused_composite_graph_is_checked_once_per_node():
    definitions = {"K0": []}
    for index in range(1, 15):
        definitions[f"K{index}"] = [StepSpec(keyword=f"K{index-1}"), StepSpec(keyword=f"K{index-1}")]
    suite = SuiteSpec(name="DAG", keywords=dict(reversed(list(definitions.items()))), cases=[CaseSpec(name="unused")])
    with patch.object(executor_module, "normalize_keyword_name", wraps=executor_module.normalize_keyword_name) as normalize:
        result = SuiteExecutor(KeywordRegistry, dry_run=True).run_suite(suite)
    assert result.passed
    assert normalize.call_count <= 3 * len(definitions)


@pytest.mark.parametrize("encoded", ["a%2bb", "a%2Bb", "%61%2b%62"])
def test_url_and_bare_percent_spellings_use_decoded_secrets(encoded):
    redactor = Redactor({"password": "a+b"})
    assert encoded not in redactor.redact("failed https://local.test/?value=" + encoded)
    if not encoded.startswith("%61"):
        assert encoded not in redactor.redact("failed credential " + encoded)
    redactor = Redactor("https://user:a%2Bb%20c@local.test/")
    assert redactor.redact("failed credential a+b c") == "failed credential ***"


@pytest.mark.parametrize("number", [0, 1, 123456])
def test_numeric_secret_aliases_are_masked_only_in_arguments(number, tmp_path):
    received = []
    def factory():
        registry = KeywordRegistry()
        registry.register("Input", lambda value: received.append(value))
        return registry
    suite = SuiteSpec(name="Numeric alias", cases=[CaseSpec(name="case", steps=[
        StepSpec(keyword="Input", args=[number], sensitive_args=[0]),
        StepSpec(keyword="Input", args=[number], kwargs={}),
    ])])
    executor = SuiteExecutor(factory)
    result = executor.run_suite(suite)
    assert received == [number, number]
    assert all(step.arguments == ["***"] for step in result.case_results[0].step_results)
    payload = json.loads(write_case_results(tmp_path / "result.json", result, redactor=executor.redactor).read_text())
    assert payload["passed_cases"] == 1 and payload["failed_cases"] == 0
    assert payload["cases"][0]["steps"][1]["retry_attempt"] == 1


def test_sensitive_variable_aliases_use_case_scopes_without_changing_actions():
    received = []
    def factory():
        registry = KeywordRegistry()
        registry.register("Input", lambda value: received.append(value))
        return registry
    suite = SuiteSpec(name="Alias", variables={"password": "${alias}", "alias": "${cred}", "cred": "PRIVATE_SUITE_ALIAS"},
        cases=[CaseSpec(name="suite", steps=[StepSpec(keyword="Input", args=["${password}"])]),
               CaseSpec(name="case", variables={"cred": "PRIVATE_CASE_ALIAS"}, steps=[StepSpec(keyword="Input", args=["${password}"])])])
    executor = SuiteExecutor(factory)
    result = executor.run_suite(suite)
    assert received == ["PRIVATE_SUITE_ALIAS", "PRIVATE_CASE_ALIAS"]
    for payload in (result.to_dict(), executor.redactor.redact_suite(suite.model_dump())):
        text = json.dumps(payload)
        assert "PRIVATE_SUITE_ALIAS" not in text and "PRIVATE_CASE_ALIAS" not in text


@pytest.mark.parametrize("failure_at", [1, 3])
def test_factory_initialization_errors_keep_collected_secrets(failure_at):
    secret = "PRIVATE_FACTORY_PASSWORD"
    created = 0
    def factory():
        nonlocal created
        created += 1
        if created == failure_at:
            raise RuntimeError("initialization failed " + secret)
        registry = KeywordRegistry()
        registry.register("Input", lambda value: None)
        return registry
    suite = SuiteSpec(name="Factory", variables={"password": "${cred}", "cred": secret},
        cases=[CaseSpec(name="case", steps=[StepSpec(keyword="Input", args=["${password}"])])])
    executor = SuiteExecutor(factory)
    result = executor.run_suite(suite)
    assert not result.passed
    assert secret in executor.redactor.secrets
    assert secret not in json.dumps(result.to_dict())


def test_empty_credentials_are_ignored_without_recursion():
    redactor = Redactor({"password": "", "api_token": None, "cookie": [""]})
    assert redactor.secrets == set()
    assert redactor.redact("ordinary text") == "ordinary text"
