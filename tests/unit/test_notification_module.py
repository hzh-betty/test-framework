import unittest

from framework.notify.dingtalk_notifier import DingTalkNotifier
from framework.notify.email_notifier import EmailNotifier, SmtpConfig


class FakeSmtpClient:
    def __init__(self):
        self.logged_in = None
        self.messages = []
        self.closed = False

    def login(self, username: str, password: str):
        self.logged_in = (username, password)

    def send_message(self, message):
        self.messages.append(message)

    def quit(self):
        self.closed = True


class QuitFailSmtpClient(FakeSmtpClient):
    def login(self, username: str, password: str):
        raise ConnectionError("auth failed")

    def quit(self):
        raise RuntimeError("quit failed")


class SendSuccessQuitFailClient(FakeSmtpClient):
    def quit(self):
        raise RuntimeError("quit failed")


class TestNotificationModule(unittest.TestCase):
    def test_email_notifier_sends_message_via_smtp(self):
        fake_client = FakeSmtpClient()
        notifier = EmailNotifier(
            config=SmtpConfig(
                host="smtp.example.com",
                port=465,
                username="bot@example.com",
                password="secret",
                sender="bot@example.com",
                receivers=["qa@example.com"],
                use_ssl=True,
            ),
            smtp_factory=lambda _config: fake_client,
        )

        notifier.send(subject="Smoke Result", body="1 passed, 0 failed")

        self.assertEqual(fake_client.logged_in, ("bot@example.com", "secret"))
        self.assertEqual(len(fake_client.messages), 1)
        self.assertTrue(fake_client.closed)

    def test_dingtalk_notifier_posts_markdown_payload(self):
        captured = {}

        def fake_sender(url: str, payload: dict):
            captured["url"] = url
            captured["payload"] = payload
            return 200

        notifier = DingTalkNotifier(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=token",
            sender=fake_sender,
        )
        notifier.send(title="Smoke", text="测试通过")

        self.assertIn("oapi.dingtalk.com", captured["url"])
        self.assertEqual(captured["payload"]["msgtype"], "markdown")
        self.assertIn("Smoke", captured["payload"]["markdown"]["title"])

    def test_dingtalk_notifier_retries_before_success(self):
        attempts = {"count": 0}

        def flaky_sender(_url: str, _payload: dict):
            attempts["count"] += 1
            if attempts["count"] == 1:
                return 500
            return 200

        notifier = DingTalkNotifier(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=token",
            sender=flaky_sender,
            retries=1,
        )

        notifier.send(title="Smoke", text="retry")
        self.assertEqual(attempts["count"], 2)

    def test_dingtalk_notifier_retries_when_sender_raises(self):
        attempts = {"count": 0}

        def flaky_sender(_url: str, _payload: dict):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise TimeoutError("network timeout")
            return 200

        notifier = DingTalkNotifier(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=token",
            sender=flaky_sender,
            retries=1,
        )

        notifier.send(title="Smoke", text="retry")
        self.assertEqual(attempts["count"], 2)

    def test_email_notifier_retries_when_factory_fails(self):
        attempts = {"count": 0}
        fake_client = FakeSmtpClient()

        def flaky_factory(_config):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ConnectionError("smtp unreachable")
            return fake_client

        notifier = EmailNotifier(
            config=SmtpConfig(
                host="smtp.example.com",
                port=465,
                username="bot@example.com",
                password="secret",
                sender="bot@example.com",
                receivers=["qa@example.com"],
                use_ssl=True,
                retries=1,
            ),
            smtp_factory=flaky_factory,
        )

        notifier.send(subject="Smoke Result", body="retry")
        self.assertEqual(attempts["count"], 2)

    def test_email_notifier_preserves_primary_error_when_quit_fails(self):
        notifier = EmailNotifier(
            config=SmtpConfig(
                host="smtp.example.com",
                port=465,
                username="bot@example.com",
                password="secret",
                sender="bot@example.com",
                receivers=["qa@example.com"],
                use_ssl=True,
                retries=0,
            ),
            smtp_factory=lambda _config: QuitFailSmtpClient(),
        )

        with self.assertRaises(RuntimeError) as ctx:
            notifier.send(subject="Smoke Result", body="retry")
        self.assertIn("auth failed", str(ctx.exception))

    def test_email_notifier_does_not_retry_when_send_succeeds_but_quit_fails(self):
        client = SendSuccessQuitFailClient()
        notifier = EmailNotifier(
            config=SmtpConfig(
                host="smtp.example.com",
                port=465,
                username="bot@example.com",
                password="secret",
                sender="bot@example.com",
                receivers=["qa@example.com"],
                use_ssl=True,
                retries=2,
            ),
            smtp_factory=lambda _config: client,
        )

        notifier.send(subject="Smoke Result", body="ok")
        self.assertEqual(len(client.messages), 1)


if __name__ == "__main__":
    unittest.main()
