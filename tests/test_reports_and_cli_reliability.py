import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import webtest_core.cli as cli
from webtest_core.dsl import DslValidationError
from webtest_core.integrations.notifications import NotificationChannel, NotificationDispatcher, WebhookClient, DingtalkSender, FeishuSender
from webtest_core.reports import build_statistics, merge_case_results, read_failed_case_names, write_allure_results, write_case_results, write_html_report, write_statistics
from webtest_core.reports.case_results import read_case_results
from webtest_core.reports.io import write_json
from webtest_core.runtime import CaseAttempt, CaseResult, StepResult, SuiteResult


def latest(root):
    return Path(json.loads((root / "latest-run.json").read_text(encoding="utf-8"))["directory"])


def write_suite(tmp_path, steps=None, name="CLI", setup=None):
    import yaml
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump({"suite": {"name": name, "setup": setup or [],
        "cases": [{"name": "case", "steps": steps or []}]}}, allow_unicode=True), encoding="utf-8")
    return path


def test_merge_retains_cross_suite_case_identity_and_lifecycle_failure(tmp_path):
    first = SuiteResult("A", [CaseResult("Login", False)], teardown_steps=[StepResult("Cleanup", False, error_message="cleanup failed", failure_type="action")])
    second = SuiteResult("B", [CaseResult("Login", True)])
    paths = [write_case_results(tmp_path / "a.json", first), write_case_results(tmp_path / "b.json", second)]
    merged = merge_case_results(paths)
    assert merged.total_cases == 2 and merged.failed_cases == 1
    assert [(case.suite, case.name) for case in merged.case_results] == [("A", "Login"), ("B", "Login")]
    assert not merged.passed
    assert merged.suite_teardown_failed
    assert merged.suite_results[0].suite_teardown_failed
    saved = write_case_results(tmp_path / "merged.json", merged)
    reloaded = read_case_results(saved)
    assert not reloaded.passed and reloaded.suite_results[0].teardown_steps[0].error_message == "cleanup failed"
    assert read_failed_case_names(saved, suite_name="A") == {"Login"}
    assert read_failed_case_names(saved, suite_name="B") == set()
    with pytest.raises(DslValidationError, match="do not contain"):
        read_failed_case_names(saved, suite_name="unknown")


def test_merge_rerun_wins_without_losing_other_suites(tmp_path):
    a = write_case_results(tmp_path / "a.json", SuiteResult("A", [CaseResult("Login", False)]))
    b = write_case_results(tmp_path / "b.json", SuiteResult("B", [CaseResult("Login", False)]))
    merged = write_case_results(tmp_path / "merged.json", merge_case_results([a, b]))
    rerun = write_case_results(tmp_path / "rerun.json", SuiteResult("A", [CaseResult("Login", True)]))
    result = merge_case_results([merged, rerun])
    assert result.total_cases == 2 and result.passed_cases == 1 and result.failed_cases == 1


def test_results_round_trip_both_retry_levels(tmp_path):
    step = StepResult("Group", True, retry_attempt=2, retry_trace=[{"attempt": 1, "error": "first failure"}],
                      children=[StepResult("Child", True)])
    case = CaseResult("Retry", True, step_results=[step], attempts=[
        CaseAttempt(1, False, [StepResult("Fail", False)], "fail", "assertion"), CaseAttempt(2, True, [step])])
    original = SuiteResult("RoundTrip", [case])
    restored = read_case_results(write_case_results(tmp_path / "results.json", original))
    assert restored.to_dict() == original.to_dict()


@pytest.mark.parametrize("payload", [{"suite": "A", "cases": [{"name": "case", "passed": "false"}]},
    {"suite": "A", "cases": [{"name": "case", "passed": True, "blocked": True}]},
    {"suite": "A", "cases": [], "total_cases": 1},
    {"suite": "A", "cases": [], "suite_teardown_failed": True}, []])
def test_historical_results_cannot_fabricate_success(payload, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DslValidationError):
        read_case_results(path)


def test_atomic_json_write_preserves_previous_file_on_serialization_failure(tmp_path):
    path = write_json(tmp_path / "results.json", {"good": True})
    with pytest.raises(TypeError):
        write_json(path, {"bad": object()})
    assert json.loads(path.read_text(encoding="utf-8")) == {"good": True}
    assert list(tmp_path.iterdir()) == [path]


def test_duplicate_case_tags_count_once():
    stats = build_statistics(SuiteResult("A", [CaseResult("case", True, tags=["smoke", "Smoke", "smoke"])]))
    assert stats["overall"]["total"] == stats["tag"]["smoke"]["total"] == 1


def test_allure_attachments_are_local_redacted_and_missing_files_omitted(tmp_path):
    dsl = tmp_path / "suite.yaml"
    dsl.write_text("suite:\n  name: Secrets\n  variables:\n    api_token: PRIVATE_TOKEN\n  cases:\n    - name: case\n      steps:\n        - keyword: Type Text\n          args: [id=password, PRIVATE_PASSWORD]\n", encoding="utf-8")
    result = SuiteResult("A", [CaseResult("case", True)])
    output = write_allure_results(tmp_path / "allure", result, dsl_path=str(dsl), runtime_log_path=str(tmp_path / "missing.log"))
    payload = json.loads(next(output.glob("*-result.json")).read_text(encoding="utf-8"))
    assert not any(item["name"] == "runtime.log" for item in payload["attachments"])
    for attachment in payload["attachments"]:
        assert Path(attachment["source"]).name == attachment["source"]
        assert (output / attachment["source"]).is_file()
    assert "PRIVATE_TOKEN" not in "".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    assert "PRIVATE_PASSWORD" not in "".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    with pytest.raises(ValueError, match="empty directory"):
        write_allure_results(output, result)


def test_html_shows_empty_suite_failure_and_escapes_errors(tmp_path):
    result = SuiteResult("Empty", setup_steps=[StepResult("Init", False, error_message="<script>bad</script>")])
    text = write_html_report(tmp_path, result, build_statistics(result)).read_text(encoding="utf-8")
    assert "运行状态：失败" in text
    assert "&lt;script&gt;bad&lt;/script&gt;" in text
    assert "<script>bad</script>" not in text


@pytest.mark.parametrize("phase", ["setup", "teardown", "run"])
def test_allure_lifecycle_errors_are_redacted(tmp_path, phase):
    secret = "PRIVATE_LIFECYCLE_SECRET"
    failure = StepResult("Init", False, kwargs={"password": secret}, error_message=f"failed with {secret}")
    result = SuiteResult("Empty", setup_steps=[failure] if phase == "setup" else [],
                         teardown_steps=[failure] if phase == "teardown" else [],
                         error_message=f"run failed with {secret}" if phase == "run" else None)
    if phase == "run":
        result.setup_steps = [failure]
    output = write_allure_results(tmp_path / "allure", result)
    assert secret not in "".join(path.read_text(encoding="utf-8") for path in output.iterdir())


@pytest.mark.parametrize("writer", ["json", "html", "statistics"])
def test_report_writers_redact_raw_result_errors_and_preserve_input(tmp_path, writer):
    secret = "PRIVATE_SECRET<&>"
    failure = StepResult("Init", False, kwargs={"password": secret}, error_message=f"step failed with {secret}")
    result = SuiteResult("Empty", setup_steps=[failure], error_message=f"run failed with {secret}")
    if writer == "json":
        output = write_case_results(tmp_path / "case-results.json", result)
    elif writer == "statistics":
        output = write_statistics(tmp_path / "statistics.json", result)
    else:
        output = write_html_report(tmp_path, result, build_statistics(result))
    assert "PRIVATE_SECRET" not in output.read_text(encoding="utf-8")
    assert failure.kwargs["password"] == secret
    assert secret in result.error_message


def test_cli_isolates_runs_and_honors_report_logging_configuration(tmp_path):
    suite = write_suite(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text("reports:\n  html: true\n  allure: true\nlogging:\n  file: custom.log\n", encoding="utf-8")
    root = tmp_path / "out"
    args = ["run", str(suite), "--config", str(config), "--dry-run", "--output-dir", str(root)]
    assert cli.main(args) == 0
    first = latest(root)
    assert (first / "custom.log").is_file() and (first / "html-report" / "index.html").is_file()
    assert (first / "allure-results" / "environment.properties").is_file()
    assert cli.main([*args, "--no-html-report", "--no-allure"]) == 0
    second = latest(root)
    assert first != second and (first / "case-results.json").is_file()
    assert not (second / "html-report").exists() and not (second / "allure-results").exists()


def test_cli_cleanup_failure_writes_current_report_and_returns_failure(tmp_path, monkeypatch):
    suite = write_suite(tmp_path, [{"keyword": "Open", "args": ["https://local.test"]}])
    closed = []

    def create(config):
        used = []
        def close():
            if used:
                closed.append(1)
                raise RuntimeError("close failed")
        return SimpleNamespace(open=lambda url: used.append(url), diagnostics=lambda: {}, close_all=close)

    monkeypatch.setattr(cli.BrowserSessionActions, "create", create)
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--output-dir", str(root)]) == 1
    payload = json.loads((latest(root) / "case-results.json").read_text(encoding="utf-8"))
    assert payload["passed"] is False and payload["failed_cases"] == 1
    assert payload["cases"][0]["steps"][-1]["error_message"] == "close failed"
    assert closed == [1]


def test_cli_preflight_prevents_deployment_for_invalid_dsl(tmp_path, monkeypatch):
    suite = write_suite(tmp_path, [{"keyword": "Open"}])
    monkeypatch.setattr(cli, "run_deploy_command", lambda *a, **k: pytest.fail("deployed invalid suite"))
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--deploy", "--output-dir", str(root)]) == 1
    assert json.loads((latest(root) / "case-results.json").read_text(encoding="utf-8"))["failure_type"] == "validation"


def test_dry_run_does_not_deploy_or_notify(tmp_path, monkeypatch):
    suite = write_suite(tmp_path)
    monkeypatch.setattr(cli, "run_deploy_command", lambda *a, **k: pytest.fail("dry-run deployed"))
    monkeypatch.setattr(cli.NotificationDispatcher, "send", lambda *a, **k: pytest.fail("dry-run notified"))
    assert cli.main(["run", str(suite), "--dry-run", "--deploy", "--notify", "--output-dir", str(tmp_path / "out")]) == 0


def test_cli_notification_errors_are_saved_visible_and_do_not_change_test_outcome(tmp_path, monkeypatch, capsys):
    suite = write_suite(tmp_path)
    root = tmp_path / "out"
    monkeypatch.setattr(cli.NotificationDispatcher, "send", lambda *a, **k: ["sender failed"])
    assert cli.main(["run", str(suite), "--notify", "--output-dir", str(root)]) == 0
    result = json.loads((latest(root) / "case-results.json").read_text(encoding="utf-8"))
    assert result["notification_errors"] == ["sender failed"]
    assert "Notification failed: sender failed" in capsys.readouterr().err


def test_suite_lifecycle_failure_triggers_failure_notification_even_with_zero_cases():
    sent = []
    sender = SimpleNamespace(send=lambda payload: sent.append(payload))
    result = SuiteResult("Empty", teardown_steps=[StepResult("Cleanup", False)])
    dispatcher = NotificationDispatcher([NotificationChannel("memory", trigger="on_failure", sender=sender)])
    assert dispatcher.send(result, statistics=build_statistics(result)) == []
    assert len(sent) == 1 and sent[0]["success"] is False


def test_webhook_response_is_closed(monkeypatch):
    from webtest_core.integrations import notifications
    closed = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): closed.append(True)
        def read(self): return b"{}"
    monkeypatch.setattr(notifications.request, "urlopen", lambda *a, **k: Response())
    WebhookClient().post_json("https://local.test", {})
    assert closed == [True]


@pytest.mark.parametrize("sender, body", [(DingtalkSender, b'{"errcode":1,"errmsg":"rejected"}'),
                                         (FeishuSender, b'{"code":1,"msg":"rejected"}')])
def test_robot_application_errors_are_not_silent(sender, body):
    client = SimpleNamespace(post_json=lambda *a, **k: body)
    with pytest.raises(RuntimeError, match="rejected"):
        sender("https://local.test", client).send({"suite": "A", "total": 1, "passed": 1, "failed": 0})


def test_deploy_timeout_is_reported_and_empty_suite_still_fails(tmp_path, monkeypatch):
    import subprocess
    suite = tmp_path / "suite.yaml"
    suite.write_text("suite:\n  name: Empty\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text("pipeline:\n  deploy:\n    timeout: 1\n    commands: [[fake]]\n", encoding="utf-8")
    def timed_out(*args, **kwargs):
        assert kwargs["timeout"] == 1
        raise subprocess.TimeoutExpired("fake", 1)
    monkeypatch.setattr(cli, "run_deploy_command", timed_out)
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--config", str(config), "--deploy", "--run-empty-suite", "--output-dir", str(root)]) == 1
    result = json.loads((latest(root) / "case-results.json").read_text(encoding="utf-8"))
    assert result["failure_type"] == "deploy" and "timed out" in result["error_message"]


def test_bad_workers_and_runtime_config_fail_clearly(tmp_path):
    suite = write_suite(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["run", str(suite), "--workers", "0"])
    config = tmp_path / "config.yaml"
    config.write_text("headles: true", encoding="utf-8")
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--config", str(config), "--output-dir", str(root)]) == 1
    assert json.loads((latest(root) / "case-results.json").read_text(encoding="utf-8"))["failure_type"] == "validation"


def test_password_keyword_kwargs_are_redacted_in_dsl_attachment(tmp_path):
    dsl = write_suite(tmp_path, [{"keyword": "TYPE__TEXT", "kwargs": {"locator": "id=password", "text": "PRIVATE_PASSWORD"}}])
    output = write_allure_results(tmp_path / "allure", SuiteResult("A", [CaseResult("case", True)]), dsl_path=str(dsl))
    assert "PRIVATE_PASSWORD" not in "".join(path.read_text(encoding="utf-8") for path in output.iterdir())


def test_history_case_cannot_claim_a_different_suite(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"suite": "A", "cases": [{"suite": "B", "name": "case", "passed": True}]}), encoding="utf-8")
    with pytest.raises(DslValidationError, match="identity"):
        read_case_results(path)


def test_deploy_failure_dispatches_configured_webhook(tmp_path, monkeypatch):
    suite = write_suite(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text("pipeline:\n  deploy:\n    commands: [[fake]]\nnotifications:\n  channels:\n    - type: webhook\n      trigger: on_failure\n      webhook: https://local.test\n", encoding="utf-8")
    sent = []
    monkeypatch.setattr(cli, "run_deploy_command", lambda *a, **k: SimpleNamespace(returncode=7, stdout="", stderr="deployment failed"))
    monkeypatch.setattr(cli, "WebhookSender", lambda url: SimpleNamespace(send=lambda payload: sent.append(payload)))
    assert cli.main(["run", str(suite), "--config", str(config), "--deploy", "--notify", "--output-dir", str(tmp_path / "out")]) == 1
    assert len(sent) == 1 and sent[0]["success"] is False and sent[0]["blocked"] == 1
    assert "deployment failed" in sent[0]["error_message"]


def test_real_deploy_timeout_stops_direct_process(tmp_path):
    import sys
    import time
    from webtest_core.dsl import RuntimeConfig, SuiteSpec
    args = cli.build_parser().parse_args(["run", "suite.yaml", "--deploy"])
    config = RuntimeConfig.model_validate({"pipeline": {"deploy": {
        "commands": [[sys.executable, "-c", "import time; time.sleep(5)"]], "timeout": 0.1}}})
    started = time.perf_counter()
    result = cli._run_deploy_if_needed(args, config, SuiteSpec(name="Timeout"))
    assert time.perf_counter() - started < 2
    assert not result.passed and result.failure_type == "deploy"
