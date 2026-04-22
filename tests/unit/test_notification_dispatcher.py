import unittest

from framework.executor.models import CaseExecutionResult, SuiteExecutionResult
from framework.notify.dispatcher import NotificationDispatcher, build_notification_summary
from framework.notify.webhook_notifier import WebhookNotifier


class RecordingNotifier:
    def __init__(self):
        self.messages = []

    def send(self, **kwargs):
        self.messages.append(kwargs)


class FailingNotifier:
    def send(self, **_kwargs):
        raise RuntimeError("network down")


class TestNotificationDispatcher(unittest.TestCase):
    def test_webhook_notifier_posts_markdown_payloads_for_wecom_and_feishu(self):
        captured = []

        def sender(url: str, payload: dict):
            captured.append((url, payload))
            return 200

        WebhookNotifier(
            kind="wecom",
            webhook="https://qyapi.weixin.qq.com/webhook/send?key=token",
            sender=sender,
        ).send(title="Smoke", text="通过")
        WebhookNotifier(
            kind="feishu",
            webhook="https://open.feishu.cn/open-apis/bot/v2/hook/token",
            sender=sender,
        ).send(title="Smoke", text="通过")

        self.assertEqual(captured[0][1]["msgtype"], "markdown")
        self.assertIn("通过", captured[0][1]["markdown"]["content"])
        self.assertEqual(captured[1][1]["msg_type"], "interactive")
        self.assertIn("Smoke", str(captured[1][1]["card"]))

    def test_dispatcher_honors_triggers_and_continues_after_channel_error(self):
        success = RecordingNotifier()
        failure = RecordingNotifier()
        always = RecordingNotifier()
        dispatcher = NotificationDispatcher(
            channels=[
                ("success", "on_success", success),
                ("failure", "on_failure", failure),
                ("always", "always", always),
                ("broken", "always", FailingNotifier()),
            ]
        )
        result = SuiteExecutionResult(
            name="NotifySuite",
            total_cases=1,
            passed_cases=0,
            failed_cases=1,
            case_results=[
                CaseExecutionResult(
                    name="Login",
                    passed=False,
                    module="auth",
                    owner="alice",
                    failure_type="assertion",
                    error_message="mismatch",
                )
            ],
        )

        errors = dispatcher.send(result=result, statistics={"overall": {"pass_rate": 0.0}})

        self.assertEqual(success.messages, [])
        self.assertEqual(len(failure.messages), 1)
        self.assertEqual(len(always.messages), 1)
        self.assertIn("broken", errors[0])
        self.assertIn("Login", failure.messages[0]["text"])

    def test_success_summary_omits_failure_details(self):
        result = SuiteExecutionResult(
            name="NotifySuite",
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            case_results=[CaseExecutionResult(name="Login", passed=True, module="auth")],
        )

        summary = build_notification_summary(result, statistics={"overall": {"pass_rate": 100.0}})

        self.assertIn("通过率: 100.0%", summary.text)
        self.assertNotIn("失败用例", summary.text)


if __name__ == "__main__":
    unittest.main()
