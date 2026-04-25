"""通知发送与调度。

调度器接收完整的执行结果，再根据触发条件决定是否发送。具体发送器只负责
协议细节，这样重试和触发策略可以集中测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import json
import smtplib
from typing import Literal, Protocol
from urllib import request

from webtest_core.runtime import SuiteResult


class NotificationSender(Protocol):
    def send(self, payload: dict) -> None:
        ...


class WebhookClient:
    """发送 JSON webhook 的最小客户端，方便通知发送器在测试中替换。"""

    def post_json(self, url: str, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        request.urlopen(req, timeout=10)


class WebhookSender:
    def __init__(self, url: str, client: WebhookClient | None = None):
        self.url = url
        self.client = client or WebhookClient()

    def send(self, payload: dict) -> None:
        self.client.post_json(self.url, payload)


class DingtalkSender:
    """钉钉机器人通知发送器。

    钉钉机器人要求消息体带 ``msgtype``，这里使用 markdown 格式，让测试结果在群
    消息中更易读。
    """

    def __init__(self, url: str, client: WebhookClient | None = None):
        self.url = url
        self.client = client or WebhookClient()

    def send(self, payload: dict) -> None:
        title = _notification_title(payload)
        self.client.post_json(
            self.url,
            {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": _markdown_summary(payload),
                },
            },
        )


class FeishuSender:
    """飞书机器人通知发送器。"""

    def __init__(self, url: str, client: WebhookClient | None = None):
        self.url = url
        self.client = client or WebhookClient()

    def send(self, payload: dict) -> None:
        self.client.post_json(
            self.url,
            {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": _notification_title(payload),
                            "content": [
                                [
                                    {
                                        "tag": "text",
                                        "text": _plain_summary(payload),
                                    }
                                ],
                            ],
                        }
                    }
                },
            },
        )


class EmailSender:
    """邮件通知使用的 SMTP 发送器。"""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        receivers: list[str],
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.receivers = receivers

    def send(self, payload: dict) -> None:
        message = EmailMessage()
        message["Subject"] = f"WebTest {payload['suite']} failed={payload['failed']}"
        message["From"] = self.sender
        message["To"] = ", ".join(self.receivers)
        message.set_content(str(payload))
        with smtplib.SMTP_SSL(self.host, self.port) as client:
            client.login(self.username, self.password)
            client.send_message(message)


@dataclass
class NotificationChannel:
    type: str
    enabled: bool = True
    trigger: Literal["always", "on_failure", "on_success"] = "always"
    retries: int = 0
    sender: NotificationSender | None = None


class NotificationDispatcher:
    def __init__(self, channels: list[NotificationChannel]):
        self.channels = channels

    def send(self, result: SuiteResult, *, statistics: dict) -> list[str]:
        errors: list[str] = []
        payload = {
            "suite": result.name,
            "total": result.total_cases,
            "passed": result.passed_cases,
            "failed": result.failed_cases,
            "statistics": statistics,
        }
        for channel in self.channels:
            if not channel.enabled or not _should_send(channel.trigger, result):
                continue
            if channel.sender is None:
                continue
            for attempt in range(channel.retries + 1):
                try:
                    channel.sender.send(payload)
                    break
                except Exception as exc:
                    if attempt >= channel.retries:
                        errors.append(str(exc))
        return errors


def _should_send(trigger: str, result: SuiteResult) -> bool:
    if trigger == "always":
        return True
    if trigger == "on_failure":
        return result.failed_cases > 0
    if trigger == "on_success":
        return result.failed_cases == 0
    return False


