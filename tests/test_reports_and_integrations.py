import json
from pathlib import Path

from webtest_core.integrations.notifications import (
    DingtalkSender,
    FeishuSender,
    NotificationChannel,
    NotificationDispatcher,
)
from webtest_core.reports import (
    build_statistics,
    merge_case_results,
    read_failed_case_names,
    write_allure_results,
    write_case_results,
    write_html_report,
)
from webtest_core.runtime import CaseResult, StepResult, SuiteResult


class MemoryNotifier:
    def __init__(self):
        self.payloads = []

    def send(self, payload: dict):
        self.payloads.append(payload)


def _suite_result() -> SuiteResult:
    return SuiteResult(
        name="ReportSuite",
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        case_results=[
            CaseResult(name="Login", passed=True, module="auth", owner="qa", tags=["smoke"]),
            CaseResult(
                name="Checkout",
                passed=False,
                module="order",
                owner="qa",
                tags=["regression"],
                failure_type="assertion",
                error_message="mismatch",
                step_results=[
                    StepResult(
                        keyword="Assert Text",
                        passed=False,
                        error_message="mismatch",
                        failure_type="assertion",
                        duration_ms=12,
                        call_chain=["Checkout", "Assert Text"],
                        retry_trace=[{"attempt": 1, "status": "failed", "error": "mismatch"}],
                        resolved_locator={"raw": "id=total", "by": "id", "value": "total"},
                        current_url="https://example.test/checkout",
                    )
                ],
            ),
        ],
    )


def test_reports_write_case_results_statistics_html_and_allure_artifacts(tmp_path: Path):
    result = _suite_result()
    output_dir = tmp_path / "artifacts"

    case_results = write_case_results(output_dir / "case-results.json", result)
    stats = build_statistics(result)
    html = write_html_report(output_dir / "html-report", result, stats)
    allure_dir = write_allure_results(output_dir / "allure-results", result)

    assert "Checkout" in case_results.read_text(encoding="utf-8")
    case_payload = json.loads(case_results.read_text(encoding="utf-8"))
    assert case_payload["suite_teardown_failed"] is False
    assert case_payload["cases"][1]["steps"][0]["duration_ms"] == 12
    assert case_payload["cases"][1]["steps"][0]["resolved_locator"]["value"] == "total"
    assert stats["overall"]["pass_rate"] == 50.0
    html_content = html.read_text(encoding="utf-8")
    assert "ReportSuite" in html_content
    assert "测试报告" in html_content
    assert "通过率" in html_content
    assert "用例" in html_content
    assert "步骤" in html_content
    assert "通过" in html_content
    assert "失败" in html_content
    assert "HTML Test Report" not in html_content
    assert "Pass Rate" not in html_content
    assert any(allure_dir.glob("*-result.json"))
    assert (allure_dir / "executor-summary.json").exists()
    assert (allure_dir / "environment.properties").exists()
    assert read_failed_case_names(case_results) == {"Checkout"}


def test_merge_case_results_uses_later_files_as_winners(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps({"suite": "Merged", "cases": [{"name": "Login", "passed": False}]}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"suite": "Merged", "cases": [{"name": "Login", "passed": True}]}),
        encoding="utf-8",
    )

    result = merge_case_results([first, second])

    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert result.case_results[0].name == "Login"


def test_notification_dispatcher_honors_failure_trigger():
    notifier = MemoryNotifier()
    dispatcher = NotificationDispatcher(
        channels=[
            NotificationChannel(
                type="memory",
                enabled=True,
                trigger="on_failure",
                sender=notifier,
            )
        ]
    )

    dispatcher.send(_suite_result(), statistics=build_statistics(_suite_result()))

    assert notifier.payloads[0]["suite"] == "ReportSuite"
    assert notifier.payloads[0]["failed"] == 1


class FakeWebhookClient:
    def __init__(self):
        self.requests = []

    def post_json(self, url: str, payload: dict):
        self.requests.append((url, payload))


def test_dingtalk_sender_builds_markdown_webhook_payload():
    client = FakeWebhookClient()
    sender = DingtalkSender("https://dingtalk.example/webhook", client=client)

    sender.send({"suite": "ReportSuite", "total": 2, "passed": 1, "failed": 1})

    assert client.requests == [
        (
            "https://dingtalk.example/webhook",
            {
                "msgtype": "markdown",
                "markdown": {
                    "title": "WebTest 测试结果：ReportSuite",
                    "text": "### WebTest 测试结果：ReportSuite\n\n- 总数：2\n- 通过：1\n- 失败：1",
                },
            },
        )
    ]


def test_feishu_sender_builds_post_webhook_payload():
    client = FakeWebhookClient()
    sender = FeishuSender("https://feishu.example/webhook", client=client)

    sender.send({"suite": "ReportSuite", "total": 2, "passed": 1, "failed": 1})

    assert client.requests == [
        (
            "https://feishu.example/webhook",
            {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": "WebTest 测试结果：ReportSuite",
                            "content": [
                                [{"tag": "text", "text": "总数：2，通过：1，失败：1"}],
                            ],
                        }
                    }
                },
            },
        )
    ]
