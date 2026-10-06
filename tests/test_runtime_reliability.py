import json
from threading import Barrier
from types import SimpleNamespace

import pytest

from webtest_core.browser import BrowserActions, BrowserConfig, BrowserSessionActions
from webtest_core.dsl import CaseSpec, StepSpec, SuiteSpec
from webtest_core.keywords import KeywordRegistry
from webtest_core.keywords.http import HttpKeywordLibrary, HttpResponse
from webtest_core.keywords.web import WebKeywordLibrary
from webtest_core.runtime import SuiteExecutor


def step(name, *args, **kwargs):
    return StepSpec(keyword=name, args=list(args), **kwargs)


def spec(steps=(), **kwargs):
    return SuiteSpec(name="Reliability", cases=[CaseSpec(name="case", steps=list(steps))], **kwargs)


def failing():
    raise AssertionError("original failure")


def test_parallel_http_cases_own_their_responses():
    barrier = Barrier(2, timeout=5)

    class Client:
        def request(self, method, url, **kwargs):
            return HttpResponse(int(url.rsplit("/", 1)[1]), {}, "{}")

    def factory():
        registry = KeywordRegistry.from_libraries([HttpKeywordLibrary(Client())])
        registry.register("Sync", lambda: barrier.wait())
        return registry

    suite = SuiteSpec(name="Parallel", cases=[CaseSpec(name=str(code), steps=[
        step("HTTP GET", f"http://local.test/{code}"), step("Sync"), step("Assert Response Status", code)
    ]) for code in [201, 202]])
    result = SuiteExecutor(factory).run_suite(suite, workers=2)
    assert result.passed_cases == 2
    assert [case.name for case in result.case_results] == ["201", "202"]


def test_parallel_browsers_own_same_alias_and_page(monkeypatch):
    barrier = Barrier(2, timeout=5)
    created = []

    class Driver:
        current_url = "about:blank"
        closed = False

        def get(self, url):
            self.current_url = url

        def quit(self):
            self.closed = True

    def create(config):
        driver = Driver()
        created.append(driver)
        return BrowserActions(driver)

    monkeypatch.setattr(BrowserActions, "create", create)

    def factory():
        actions = BrowserSessionActions(BrowserConfig())
        registry = KeywordRegistry.from_libraries([WebKeywordLibrary(actions)],
            diagnostics=actions.diagnostics, cleanup=actions.close_all)
        registry.register("Sync", lambda: barrier.wait())
        return registry

    suite = SuiteSpec(name="Browsers", cases=[CaseSpec(name=name, steps=[
        step("New Browser", "main"), step("Open", f"https://local.test/{name}"), step("Sync"),
        step("Assert URL Contains", name)
    ]) for name in ["alpha", "beta"]])
    result = SuiteExecutor(factory).run_suite(suite, workers=2)
    assert result.passed
    assert len(created) == 2
    assert all(driver.closed for driver in created)


def test_case_retry_creates_fresh_browser_and_preserves_history(monkeypatch):
    created = []
    calls = []

    def create(config):
        driver = SimpleNamespace(current_url="blank", quit=lambda: None)
        created.append(driver)
        return BrowserActions(driver)

    monkeypatch.setattr(BrowserActions, "create", create)

    def factory():
        actions = BrowserSessionActions(BrowserConfig())
        registry = KeywordRegistry.from_libraries([WebKeywordLibrary(actions)], cleanup=actions.close_all)

        def transient_service_failure():
            calls.append(1)
            if len(calls) == 1:
                failing()

        registry.register("Flaky", transient_service_failure)
        return registry

    suite = SuiteSpec(name="Retry", cases=[CaseSpec(name="case", retry=1, steps=[step("New Browser"), step("Flaky")])])
    result = SuiteExecutor(factory).run_suite(suite)
    assert result.passed
    assert len(created) == 2 and created[0] is not created[1]
    assert [attempt.passed for attempt in result.case_results[0].attempts] == [False, True]


def test_http_response_does_not_leak_between_cases():
    def factory():
        client = SimpleNamespace(request=lambda *args, **kwargs: HttpResponse(200, {}, "{}"))
        return KeywordRegistry.from_libraries([HttpKeywordLibrary(client)])

    suite = SuiteSpec(name="Responses", cases=[
        CaseSpec(name="request", steps=[step("HTTP GET", "https://local.test")]),
        CaseSpec(name="no request", steps=[step("Assert Response Status", 200)]),
    ])
    result = SuiteExecutor(factory).run_suite(suite)
    assert result.passed_cases == 1 and result.failed_cases == 1
    assert "还没有 HTTP 响应" in result.case_results[1].error_message


def test_failed_http_request_clears_previous_response():
    calls = []

    class Client:
        def request(self, *args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("connection failed")
            return HttpResponse(200, {}, "{}")

    result = SuiteExecutor(lambda: KeywordRegistry.from_libraries([HttpKeywordLibrary(Client())])).run_suite(spec([
        step("HTTP GET", "https://local.test/first"),
        step("HTTP GET", "https://local.test/second", continue_on_failure=True), step("Assert Response Status", 200)
    ]))
    assert not result.case_results[0].step_results[-1].passed
    assert "还没有 HTTP 响应" in result.case_results[0].step_results[-1].error_message


def test_http_only_run_never_creates_browser(monkeypatch):
    monkeypatch.setattr(BrowserActions, "create", lambda config: pytest.fail("HTTP run created a browser"))

    def factory():
        actions = BrowserSessionActions(BrowserConfig())
        client = SimpleNamespace(request=lambda *args, **kwargs: HttpResponse(200, {}, "{}"))
        return KeywordRegistry.from_libraries([WebKeywordLibrary(actions), HttpKeywordLibrary(client)],
            diagnostics=actions.diagnostics, cleanup=actions.close_all)

    result = SuiteExecutor(factory).run_suite(spec([step("HTTP GET", "https://local.test")]))
    assert result.passed
    assert result.case_results[0].step_results[0].current_url is None


def test_close_browser_does_not_reopen_for_diagnostics(monkeypatch):
    created, closed = [], []
    contexts = []

    def create(config):
        created.append(1)
        return BrowserActions(SimpleNamespace(current_url="blank", quit=lambda: closed.append(1)))

    monkeypatch.setattr(BrowserActions, "create", create)

    def factory():
        actions = BrowserSessionActions(BrowserConfig())
        contexts.append(actions)
        return KeywordRegistry.from_libraries([WebKeywordLibrary(actions)], diagnostics=actions.diagnostics, cleanup=actions.close_all)

    result = SuiteExecutor(factory).run_suite(spec([step("New Browser"), step("Close Browser")]))
    assert result.passed and created == closed == [1]
    assert all(not context._sessions for context in contexts)
    assert result.case_results[0].step_results[-1].current_url is None


@pytest.mark.parametrize("action_fails", [False, True])
def test_diagnostic_failure_does_not_change_action_or_skip_cleanup(action_fails):
    calls = []

    def factory():
        def diagnostics():
            raise RuntimeError("diagnostic failure")

        registry = KeywordRegistry(diagnostics=diagnostics)
        registry.register("Action", failing if action_fails else lambda: calls.append("action"))
        registry.register("Cleanup", lambda: calls.append("cleanup"))
        return registry

    result = SuiteExecutor(factory).run_suite(spec([step("Action", retry=2)], teardown=[step("Cleanup")]))
    action = result.case_results[0].step_results[0]
    assert action.passed is not action_fails
    assert action.diagnostic_error == "diagnostic failure"
    assert calls.count("action") == (0 if action_fails else 1)
    assert calls[-1] == "cleanup"
    if action_fails:
        assert action.error_message == "original failure"


def test_empty_suite_setup_failure_is_a_run_failure():
    def factory():
        registry = KeywordRegistry()
        registry.register("Fail", failing)
        return registry

    result = SuiteExecutor(factory).run_suite(SuiteSpec(name="Empty", setup=[step("Fail")]), run_empty_suite=True)
    assert not result.passed and result.failed_cases == 0
    assert result.suite_setup_failed
    assert result.setup_steps[0].error_message == "original failure"


def test_suite_setup_blocks_cases_and_preserves_assertion():
    def factory():
        registry = KeywordRegistry()
        registry.register("Fail", failing)
        return registry

    result = SuiteExecutor(factory).run_suite(spec(setup=[step("Fail")]))
    assert result.blocked_cases == 1 and result.failed_cases == 0
    assert result.case_results[0].failure_type == "assertion"
    assert result.setup_steps[0].error_message == "original failure"


def test_teardown_runs_all_cleanups_and_does_not_add_fake_cases():
    calls = []

    def factory():
        registry = KeywordRegistry()
        registry.register("Fail", failing)
        registry.register("Cleanup", lambda: calls.append("cleanup"))
        return registry

    suite = SuiteSpec(name="Teardown", cases=[CaseSpec(name="case", teardown=[step("Fail"), step("Cleanup")])],
                      teardown=[step("Fail"), step("Cleanup")])
    result = SuiteExecutor(factory).run_suite(suite)
    assert calls == ["cleanup", "cleanup"]
    assert result.total_cases == 1 and result.failed_cases == 1
    assert result.suite_teardown_failed


def test_resource_close_failures_are_structured_and_other_sessions_close():
    calls = []
    contexts = []

    def factory():
        actions = BrowserSessionActions(BrowserConfig())
        contexts.append(actions)

        def install_resources():
            def bad_close():
                calls.append("bad")
                raise RuntimeError("quit failed")
            actions._sessions = {"bad": SimpleNamespace(close_browser=bad_close),
                                 "good": SimpleNamespace(close_browser=lambda: calls.append("good"))}

        registry = KeywordRegistry(cleanup=actions.close_all)
        registry.register("Install", install_resources)
        return registry

    result = SuiteExecutor(factory).run_suite(spec([step("Install")]))
    assert calls == ["bad", "good"]
    assert result.failed_cases == 1
    assert result.case_results[0].step_results[-1].keyword == "Close Resources"
    assert all(not actions._sessions for actions in contexts)


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("bad_step", [step("Needs Arg"), step("Needs Arg", 1, 2), step("Needs Arg", kwargs={"typo": 1}),
                                      step("Needs Arg", "${missing}"), step("Needs Arg", 1, timeout="2s")])
def test_preflight_rejects_invalid_calls_before_setup(dry_run, bad_step):
    calls = []

    def factory():
        registry = KeywordRegistry()
        registry.register("Needs Arg", lambda arg: None)
        registry.register("Setup", lambda: calls.append("setup"))
        return registry

    result = SuiteExecutor(factory, dry_run=dry_run).run_suite(spec([bad_step], setup=[step("Setup")]))
    assert not result.passed and result.failure_type == "validation"
    assert calls == []


def test_composite_normalization_and_retry_preserve_child_failures():
    calls = []

    def factory():
        registry = KeywordRegistry()
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                failing()
        registry.register("Flaky", flaky)
        return registry

    result = SuiteExecutor(factory).run_suite(spec([step("my-group", retry=1)], keywords={"My Group": [step("Flaky")]}))
    parent = result.case_results[0].step_results[0]
    assert result.passed and len(calls) == 2
    assert parent.retry_attempt == 2
    assert parent.children[0].call_chain == ["my-group", "Flaky"]
    assert parent.retry_trace[0]["children"][0]["error_message"] == "original failure"


@pytest.mark.parametrize("keywords", [{"A": [step("A")]}, {"A": [step("B")], "B": [step("A")]}])
def test_composite_cycles_fail_before_execution(keywords):
    result = SuiteExecutor(KeywordRegistry).run_suite(spec([step("A")], keywords=keywords))
    assert result.failure_type == "validation" and "cycle" in result.error_message


@pytest.mark.parametrize("call", [step("Group", 1), step("Group", kwargs={"x": 1}), step("Group", timeout="1s")])
def test_composite_unsupported_parameters_are_rejected(call):
    result = SuiteExecutor(KeywordRegistry).run_suite(spec([call], keywords={"Group": []}))
    assert result.failure_type == "validation" and "do not accept" in result.error_message


def test_case_and_step_retry_histories_remain_separate():
    calls = []

    def factory():
        registry = KeywordRegistry()
        def flaky():
            calls.append(1)
            if len(calls) % 2:
                failing()
        registry.register("Flaky", flaky)
        registry.register("Fail", failing)
        return registry

    suite = SuiteSpec(name="History", cases=[CaseSpec(name="case", retry=1, steps=[step("Flaky", retry=1), step("Fail")])])
    result = SuiteExecutor(factory).run_suite(suite)
    case = result.case_results[0]
    assert len(case.attempts) == 2
    assert case.step_results[0].retry_trace[0]["attempt"] == 1
    assert len(case.step_results[0].retry_trace) == 1
    assert len(case.attempts[0].steps[0].retry_trace) == 1


def test_sensitive_values_reach_action_but_never_results_or_errors():
    received = []

    def factory():
        registry = KeywordRegistry()
        def request(**kwargs):
            received.append(kwargs)
            raise RuntimeError(f"request failed for {kwargs}")
        registry.register("Request", request)
        registry.register("Input", lambda text: received.append(text))
        return registry

    suite = spec([step("Input", "PRIVATE_POSITIONAL", sensitive_args=[0]),
                  step("Request", kwargs={"headers": {"Authorization": "Bearer PRIVATE_TOKEN"}, "password": "PRIVATE_PASSWORD"})])
    result = SuiteExecutor(factory).run_suite(suite)
    payload = json.dumps(result.to_dict())
    assert received[0] == "PRIVATE_POSITIONAL"
    assert received[1]["password"] == "PRIVATE_PASSWORD"
    for secret in ["PRIVATE_POSITIONAL", "PRIVATE_TOKEN", "PRIVATE_PASSWORD"]:
        assert secret not in payload


def test_json_missing_field_is_assertion_and_url_fragment_is_not_locator():
    def factory():
        client = SimpleNamespace(request=lambda *a, **k: HttpResponse(200, {}, "{}"))
        registry = KeywordRegistry.from_libraries([HttpKeywordLibrary(client)])
        registry.register("Assert URL Contains", lambda fragment: None)
        return registry

    result = SuiteExecutor(factory).run_suite(spec([step("Assert URL Contains", "dashboard"),
        step("HTTP GET", "https://local.test"), step("Assert Response JSON", "missing", 1)]))
    assert result.case_results[0].step_results[0].resolved_locator is None
    assert result.case_results[0].failure_type == "assertion"


def test_locator_diagnostics_use_actual_selenium_strategy():
    actions = SimpleNamespace(click=lambda locator: None)
    result = SuiteExecutor(lambda: KeywordRegistry.from_libraries([WebKeywordLibrary(actions)])).run_suite(spec([step("Click", "testid=submit")]))
    assert result.case_results[0].step_results[0].resolved_locator == {
        "raw": "testid=submit", "by": "css selector", "value": "[data-testid='submit']"}


def test_escaped_password_in_error_is_redacted():
    secret = "PRIVATE'\\\"PASSWORD"
    def factory():
        registry = KeywordRegistry()
        def request(password):
            raise RuntimeError(json.dumps({"password": password}))
        registry.register("Request", request)
        return registry
    result = SuiteExecutor(factory).run_suite(spec([step("Request", kwargs={"password": secret})]))
    assert "PRIVATE" not in result.case_results[0].error_message
