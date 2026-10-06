import json
import smtplib
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from webtest_core.integrations import notifications
from webtest_core.integrations.notifications import EmailSender, NotificationChannel, NotificationDispatcher, WebhookSender
from webtest_core.redaction import Redactor
from webtest_core.reports import build_statistics, write_allure_results, write_case_results, write_html_report, write_statistics
from webtest_core.reports.case_results import read_case_results
from webtest_core.reports.statistics import safe_statistics
from webtest_core.runtime import CaseAttempt, CaseResult, StepResult, SuiteResult


class MemorySender:
    def __init__(self, error=None):
        self.payloads = []
        self.error = error

    def send(self, payload):
        self.payloads.append(payload)
        if self.error:
            raise RuntimeError(self.error)


@pytest.mark.parametrize("phase", ["setup", "teardown"])
@pytest.mark.parametrize("merged", [False, True])
def test_allure_reports_lifecycle_failure_alongside_case_results(tmp_path, phase, merged):
    failure = StepResult("Cleanup", False, error_message="resource cleanup failed", failure_type="action")
    result = SuiteResult("A", [CaseResult("case", True, suite="A")],
                         setup_steps=[failure] if phase == "setup" else [],
                         teardown_steps=[failure] if phase == "teardown" else [])
    if merged:
        result = SuiteResult("Merged", list(result.case_results), suite_results=[result])
    output = write_allure_results(tmp_path / "allure", result)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("*-result.json")]
    assert next(item for item in payloads if item["name"] == "case")["status"] == "passed"
    failure_payload = next(item for item in payloads if item["name"] == "A::run failure")
    assert failure_payload["status"] == "broken"
    assert failure_payload["statusDetails"]["message"] == "resource cleanup failed"
    assert result.total_cases == result.passed_cases == 1


def test_allure_exports_recorded_timing_without_fabricating_missing_values(tmp_path):
    child = StepResult("Child", True, start=1002, stop=1003)
    step = StepResult("Group", True, children=[child], start=1001, stop=1004)
    case = CaseResult("case", True, step_results=[step], start=1000, stop=1005)
    result = SuiteResult("A", [case], start=999, stop=1006)
    output = write_allure_results(tmp_path / "timed", result)
    payload = json.loads(next(output.glob("*-result.json")).read_text(encoding="utf-8"))
    container = json.loads(next(output.glob("*-container.json")).read_text(encoding="utf-8"))
    assert (payload["start"], payload["stop"]) == (1000, 1005)
    assert (payload["steps"][0]["start"], payload["steps"][0]["stop"]) == (1001, 1004)
    assert payload["steps"][0]["steps"][0]["stop"] == 1003
    assert (container["start"], container["stop"]) == (999, 1006)
    missing = write_allure_results(tmp_path / "untimed", SuiteResult("B", [CaseResult("case", True)]))
    assert "start" not in json.loads(next(missing.glob("*-result.json")).read_text(encoding="utf-8"))
    assert "stop" not in json.loads(next(missing.glob("*-container.json")).read_text(encoding="utf-8"))


def test_allure_standalone_dsl_redacts_scoped_sensitive_variable_references(tmp_path):
    payload = {"suite": {"name": "Secrets", "variables": {"cred": "PRIVATE_SUITE", "alias": "${cred}"},
        "setup": [{"keyword": "TYPE__TEXT", "args": ["id=password", "${alias}"]}],
        "cases": [{"name": "case", "variables": {"cred": "PRIVATE_CASE"}, "steps": [
            {"keyword": "Input", "args": ["${cred}"], "sensitive_args": [0]}]}]}}
    dsl = tmp_path / "suite.yaml"
    dsl.write_text(yaml.safe_dump(payload), encoding="utf-8")
    output = write_allure_results(tmp_path / "allure", SuiteResult("Secrets"), dsl_path=dsl)
    attachment = next(output.glob("*-attachment.yaml")).read_text(encoding="utf-8")
    assert "PRIVATE_SUITE" not in attachment
    assert "PRIVATE_CASE" not in attachment
    assert payload["suite"]["variables"]["cred"] == "PRIVATE_SUITE"


@pytest.mark.parametrize("secret", [0, 1, 123456])
def test_allure_dsl_redacts_numeric_sensitive_values_without_changing_retry_metadata(tmp_path, secret):
    payload = {"suite": {"name": "A", "variables": {"cred": secret}, "cases": [{"name": "case", "retry": 1,
        "steps": [{"keyword": "Input", "args": ["${cred}", secret], "sensitive_args": [0, 1], "retry": 1}]}]}}
    dsl = tmp_path / "suite.yaml"
    dsl.write_text(yaml.safe_dump(payload), encoding="utf-8")
    output = write_allure_results(tmp_path / "allure", SuiteResult("A"), dsl_path=dsl)
    emitted = yaml.safe_load(next(output.glob("*-attachment.yaml")).read_text(encoding="utf-8"))["suite"]
    assert emitted["variables"]["cred"] == "***"
    assert emitted["cases"][0]["steps"][0]["args"] == ["***", "***"]
    assert emitted["cases"][0]["retry"] == emitted["cases"][0]["steps"][0]["retry"] == 1
    assert payload["suite"]["variables"]["cred"] == secret


def test_allure_redacts_input_with_external_redactor_and_preserves_protocol_status(tmp_path):
    step = StepResult("Input", True, kwargs={"password": "passed"}, error_message="used passed")
    result = SuiteResult("A", [CaseResult("case", True, step_results=[step])])
    output = write_allure_results(tmp_path, result, redactor=Redactor())
    payload = json.loads(next(output.glob("*-result.json")).read_text(encoding="utf-8"))
    assert payload["status"] == payload["steps"][0]["status"] == "passed"
    assert payload["steps"][0]["statusDetails"]["message"] == "used ***"
    assert step.kwargs["password"] == "passed"


def test_allure_keeps_distinct_suite_associations_when_names_are_redacted(tmp_path):
    suites = [SuiteResult(name, [CaseResult("case", True, suite=name)],
                          setup_steps=[StepResult(marker, True, kwargs={"password": name})])
              for name, marker in [("PRIVATE_A", "First"), ("PRIVATE_B", "Second")]]
    result = SuiteResult("Merged", [case for suite in suites for case in suite.case_results], suite_results=suites)
    output = write_allure_results(tmp_path, result)
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("*-result.json")]
    containers = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("*-container.json")]
    assert len({case["historyId"] for case in cases}) == 2
    assert len({case["testCaseId"] for case in cases}) == 2
    assert all(container["name"] == "***" and len(container["children"]) == 1 for container in containers)
    assert {child for container in containers for child in container["children"]} == {case["uuid"] for case in cases}


def test_allure_retains_case_and_suite_identity_after_masked_results_roundtrip(tmp_path):
    suites = [SuiteResult(name, [CaseResult("PRIVATE_CASE", True, suite=name)],
                          setup_steps=[StepResult("Init", True, kwargs={"password": [name, "PRIVATE_CASE"]})])
              for name in ("PRIVATE_A", "PRIVATE_B")]
    cases = [case for suite in suites for case in suite.case_results]
    for suite in suites:
        suite.case_results = []
    result = SuiteResult("Merged", cases, suite_results=[SuiteResult("Nested", suite_results=suites)])
    restored = read_case_results(write_case_results(tmp_path / "saved.json", result))
    assert all(suite.name == "***" for suite in restored.suite_results[0].suite_results)
    assert all(case.name == "***" for case in restored.case_results)
    outputs = [write_allure_results(tmp_path / "original", result), write_allure_results(tmp_path / "restored", restored)]
    payloads = [[json.loads(path.read_text(encoding="utf-8")) for path in output.glob("*-result.json")]
                for output in outputs]
    assert {(case["testCaseId"], case["historyId"]) for case in payloads[0]} == {
        (case["testCaseId"], case["historyId"]) for case in payloads[1]}
    assert len({case["testCaseId"] for case in payloads[1]}) == 2
    containers = [json.loads(path.read_text(encoding="utf-8")) for path in outputs[1].glob("*-container.json")]
    assert len(containers) == 2 and all(len(container["children"]) == 1 for container in containers)
    assert len({container["children"][0] for container in containers}) == 2


def test_allure_exports_cases_and_lifecycle_from_accepted_nested_results(tmp_path):
    case = CaseResult("case", True, suite="Leaf")
    leaf = SuiteResult("Leaf", [case], teardown_steps=[StepResult("Cleanup", False, error_message="cleanup failed")])
    result = SuiteResult("Merged", suite_results=[SuiteResult("Wrapper", suite_results=[leaf])])
    restored = read_case_results(write_case_results(tmp_path / "results.json", result))
    output = write_allure_results(tmp_path / "allure", restored)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("*-result.json")]
    emitted_case = next(item for item in payloads if item["name"] == "case")
    assert emitted_case["status"] == "passed"
    assert next(item for item in payloads if item["name"] == "Leaf::run failure")["status"] == "broken"
    container = json.loads(next(output.glob("*-container.json")).read_text(encoding="utf-8"))
    assert container["name"] == "Leaf" and container["children"] == [emitted_case["uuid"]]
    assert len(list(output.glob("*-container.json"))) == 1
    assert result.case_results == [] and leaf.case_results == [case]


def test_html_redacts_data_before_rendering_and_keeps_markup_valid(tmp_path):
    step = StepResult("Input", False, kwargs={"password": "td"}, error_message="bad td <script>")
    result = SuiteResult("A", [CaseResult("case", False, step_results=[step])])
    text = write_html_report(tmp_path, result, build_statistics(result), redactor=Redactor()).read_text(encoding="utf-8")
    assert "<td>" in text and "</td>" in text
    assert "<***>" not in text
    assert "bad *** &lt;script&gt;" in text
    assert step.error_message == "bad td <script>"


def test_html_shows_and_escapes_merged_suite_notification_errors(tmp_path):
    child = SuiteResult("Child <script>", notification_errors=["smtp <rejected>"])
    result = SuiteResult("Merged", notification_errors=["root failure"], suite_results=[child])
    text = write_html_report(tmp_path, result, build_statistics(result)).read_text(encoding="utf-8")
    assert "root failure; Child &lt;script&gt;: smtp &lt;rejected&gt;" in text
    assert "smtp <rejected>" not in text


def test_statistics_writer_uses_shared_redactor_without_changing_counts(tmp_path):
    result = SuiteResult("A", [CaseResult("case", False, error_message="failed PRIVATE_CRED")])
    redactor = Redactor({"password": "PRIVATE_CRED"})
    payload = json.loads(write_statistics(tmp_path / "stats.json", result, redactor=redactor).read_text(encoding="utf-8"))
    assert payload["overall"]["failed"] == 1
    assert payload["overall"]["failed_cases"][0]["error_message"] == "failed ***"
    assert result.case_results[0].error_message == "failed PRIVATE_CRED"


def test_statistics_redacts_dimension_labels_and_combines_masked_collisions(tmp_path):
    cases = [CaseResult("first", True, module="PRIVATE_ONE", type="PRIVATE_ONE", priority="PRIVATE_ONE",
                        owner="PRIVATE_ONE", tags=["PRIVATE_ONE", "PRIVATE_TWO"],
                        step_results=[StepResult("Input", True, kwargs={"password": "PRIVATE_ONE"})]),
             CaseResult("second", False, module="PRIVATE_TWO", type="PRIVATE_TWO", priority="PRIVATE_TWO",
                        owner="PRIVATE_TWO", tags=["PRIVATE_TWO"], failure_type="action",
                        error_message="failed PRIVATE_TWO",
                        step_results=[StepResult("Input", False, kwargs={"password": "PRIVATE_TWO"})])]
    result = SuiteResult("A", cases)
    statistics = build_statistics(result)
    for dimension in ("module", "type", "priority", "owner", "tag"):
        assert set(statistics[dimension]) == {"***"}
        assert statistics[dimension]["***"]["total"] == 2
        assert statistics[dimension]["***"]["passed"] == statistics[dimension]["***"]["failed"] == 1
        assert statistics[dimension]["***"]["failed_cases"][0]["failure_type"] == "action"
    assert "PRIVATE" not in json.dumps(statistics)
    supplied = {**statistics, "owner": {"PRIVATE_ONE": {"total": 99}},
                "custom": {"memo": "PRIVATE_TWO", "number": 9}}
    protected = safe_statistics(result, supplied)
    assert protected["owner"]["***"]["total"] == 2
    assert protected["custom"] == {"memo": "***", "number": 9}
    emitted = json.loads(write_statistics(tmp_path / "statistics.json", result, statistics=supplied).read_text(encoding="utf-8"))
    sender = MemorySender()
    assert NotificationDispatcher([NotificationChannel("memory", sender=sender)]).send(result, statistics=supplied) == []
    assert emitted == sender.payloads[0]["statistics"] == protected
    assert supplied["owner"] == {"PRIVATE_ONE": {"total": 99}}
    assert cases[0].owner == "PRIVATE_ONE" and cases[1].tags == ["PRIVATE_TWO"]


def test_statistics_and_notifications_keep_action_failure_enum_when_action_is_secret(tmp_path):
    step = StepResult("Input", False, kwargs={"password": "action"}, failure_type="action", error_message="failed action")
    case = CaseResult("case", False, step_results=[step], failure_type="action", error_message="failed action")
    result = SuiteResult("A", [case], failure_type="action", error_message="failed action")
    supplied = build_statistics(result)
    supplied["custom"] = {"message": "used action", "number": 7}
    statistics = safe_statistics(result, supplied)
    assert statistics["failure_type"] == "action"
    assert statistics["overall"]["failed_cases"][0]["failure_type"] == "action"
    assert statistics["error_message"] == "failed ***"
    assert statistics["custom"] == {"message": "used ***", "number": 7}
    written = json.loads(write_statistics(tmp_path / "statistics.json", result, statistics=supplied).read_text(encoding="utf-8"))
    sender = MemorySender()
    NotificationDispatcher([NotificationChannel("memory", sender=sender)]).send(result, statistics=supplied)
    assert written == sender.payloads[0]["statistics"] == statistics
    assert sender.payloads[0]["error_message"] == "failed ***"
    assert "failed ***" in write_html_report(tmp_path / "html", result, supplied).read_text(encoding="utf-8")
    assert result.failure_type == case.failure_type == step.failure_type == "action"
    assert supplied["custom"]["message"] == "used action"


def test_dispatcher_redacts_payload_and_errors_without_mutating_result_or_statistics():
    secret = "PRIVATE+URL TOKEN"
    step = StepResult("Init", False, kwargs={"password": secret}, error_message=f"failed {secret}")
    result = SuiteResult("A", setup_steps=[step], error_message=f"failed {secret}")
    statistics = build_statistics(result)
    statistics["error_message"] = result.error_message
    sender = MemorySender("request failed: https://local.test/?api_token=PRIVATE%2BURL%20TOKEN")
    errors = NotificationDispatcher([NotificationChannel("memory", sender=sender)]).send(
        result, statistics=statistics, redactor=Redactor())
    assert sender.payloads[0]["error_message"] == "failed ***"
    assert sender.payloads[0]["statistics"]["error_message"] == "failed ***"
    assert "PRIVATE" not in errors[0]
    assert secret in result.error_message and secret in statistics["error_message"]


def test_dispatcher_gives_each_sender_an_independent_payload():
    class MutatingSender:
        def send(self, payload):
            payload["statistics"]["overall"]["total"] = 900

    result = SuiteResult("A", [CaseResult("case", True)])
    sender = MemorySender()
    statistics = build_statistics(result)
    NotificationDispatcher([NotificationChannel("mutation", sender=MutatingSender()),
                            NotificationChannel("memory", sender=sender)]).send(result, statistics=statistics)
    assert sender.payloads[0]["statistics"]["overall"]["total"] == 1
    assert statistics["overall"]["total"] == 1


def test_dispatcher_keeps_connection_credentials_and_redacts_sender_errors():
    calls = []
    url = "https://local.test/?access_token=PRIVATE_CONNECT"

    class Client:
        def post_json(self, connection_url, payload):
            calls.append(connection_url)
            raise RuntimeError("connection failed for PRIVATE_CONNECT")

    result = SuiteResult("A", [CaseResult("case", True)])
    errors = NotificationDispatcher([NotificationChannel("webhook", sender=WebhookSender(url, client=Client()))]).send(
        result, statistics=build_statistics(result))
    assert calls == [url]
    assert errors == ["webhook: connection failed for ***"]


def email_sender():
    return EmailSender(host="smtp.test", port=465, username="user", password="PRIVATE_SMTP",
                       sender="from@test", receivers=["ok@test", "refused@test"])


def test_smtp_partial_refusal_is_reported_without_resending_accepted_mail(monkeypatch):
    calls = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, username, password):
            calls.append((username, password))

        def send_message(self, message):
            calls.append(message)
            return {"refused@test": (550, b"rejected PRIVATE_SMTP")}

    monkeypatch.setattr(notifications.smtplib, "SMTP_SSL", lambda *args, **kwargs: Client())
    result = SuiteResult("A", [CaseResult("case", True)])
    errors = NotificationDispatcher([NotificationChannel("email", retries=3, sender=email_sender())]).send(
        result, statistics=build_statistics(result))
    assert len(calls) == 2
    assert calls[0] == ("user", "PRIVATE_SMTP")
    assert len(errors) == 1 and "refused@test" in errors[0] and "550" in errors[0]
    assert "PRIVATE_SMTP" not in errors[0]
    assert calls[1]["To"] == "ok@test, refused@test"


@pytest.mark.parametrize("failure", [smtplib.SMTPRecipientsRefused({"refused@test": (450, b"retry")}), OSError("offline")])
def test_smtp_complete_failures_keep_configured_retry_behavior(monkeypatch, failure):
    calls = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, username, password):
            pass

        def send_message(self, message):
            calls.append(message)
            if len(calls) == 1:
                raise failure
            return {}

    monkeypatch.setattr(notifications.smtplib, "SMTP_SSL", lambda *args, **kwargs: Client())
    result = SuiteResult("A", [CaseResult("case", True)])
    errors = NotificationDispatcher([NotificationChannel("email", retries=1, sender=email_sender())]).send(
        result, statistics=build_statistics(result))
    assert errors == [] and len(calls) == 2


@pytest.mark.parametrize("writer", ["allure", "html"])
def test_reports_copy_recorded_screenshots_and_keep_sources_and_result_unchanged(tmp_path, writer):
    screenshot = tmp_path / "PRIVATE_CRED screenshot.png"
    image = b"\x89PNG\r\n\x1a\nrecorded screenshot"
    screenshot.write_bytes(image)
    unrelated = tmp_path / "private.txt"
    unrelated.write_text("do not copy", encoding="utf-8")
    attachments = [{"name": '截图 <script> "click"', "source": str(screenshot), "type": "image/png"},
                   {"name": "missing", "source": str(tmp_path / "missing.png"), "type": "image/png"},
                   {"name": "disguised", "source": str(unrelated), "type": "image/png"},
                   {"name": "unknown", "source": str(unrelated), "type": "text/plain"}]
    child = StepResult("Screenshot", True, attachments=attachments)
    group = StepResult("Group", True, children=[child])
    case = CaseResult("case", True, step_results=[group], attempts=[CaseAttempt(1, True, [group])])
    result = SuiteResult("A", [case], setup_steps=[StepResult("Init", True, attachments=[attachments[0]])])
    redactor = Redactor({"password": "PRIVATE_CRED"})
    if writer == "allure":
        output = write_allure_results(tmp_path / "allure", result, redactor=redactor)
        payload = json.loads(next(output.glob("*-result.json")).read_text(encoding="utf-8"))
        emitted = payload["steps"][0]["steps"][0]["attachments"]
        assert len(emitted) == 1 and emitted[0]["type"] == "image/png"
        copied = output / emitted[0]["source"]
        assert list(output.glob("*-attachment.png")) == [copied]
    else:
        output = write_html_report(tmp_path / "html", result, build_statistics(result), redactor=redactor)

        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.hrefs = []

            def handle_starttag(self, tag, attrs):
                if tag == "a":
                    self.hrefs.append(dict(attrs)["href"])

        text = output.read_text(encoding="utf-8")
        links = Links()
        links.feed(text)
        assert links.hrefs and len(set(links.hrefs)) == 1
        assert "截图 &lt;script&gt; &quot;click&quot;" in text
        copied = output.parent / links.hrefs[0]
        assert list((output.parent / "attachments").iterdir()) == [copied]
    assert copied.read_bytes() == image
    assert screenshot.read_bytes() == image
    assert child.attachments == attachments
    assert Path(child.attachments[0]["source"]).is_absolute()
    assert unrelated.read_text(encoding="utf-8") == "do not copy"
