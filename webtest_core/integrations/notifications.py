"""通知发送与调度。

调度器接收完整的执行结果，再根据触发条件决定是否发送。具体发送器只负责
协议细节，这样重试和触发策略可以集中测试。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from email.message import EmailMessage
import json
import smtplib
from typing import Literal, Protocol
from urllib import request

from webtest_core.redaction import Redactor
from webtest_core.reports.statistics import safe_statistics
from webtest_core.runtime import SuiteResult


class NotificationSender(Protocol):
    def send(self, payload: dict) -> None:
        ...


class WebhookClient:
    """发送 JSON webhook 的最小客户端，方便通知发送器在测试中替换。"""

    def post_json(self, url: str, payload: dict) -> bytes:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with request.urlopen(req, timeout=10) as response:
            return response.read()


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
        response = self.client.post_json(
            self.url,
            {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": _markdown_summary(payload),
                },
            },
        )
        _check_bot_response(response, "errcode")


class FeishuSender:
    """飞书机器人通知发送器。"""

    def __init__(self, url: str, client: WebhookClient | None = None):
        self.url = url
        self.client = client or WebhookClient()

    def send(self, payload: dict) -> None:
        response = self.client.post_json(
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
        _check_bot_response(response, "code")


class _PartialEmailDeliveryError(smtplib.SMTPRecipientsRefused):
    """部分收件人已接收；再次发送会给他们重复邮件。"""


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
        timeout: float = 10,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.receivers = receivers
        self.timeout = timeout

    def send(self, payload: dict) -> None:
        message = EmailMessage()
        message["Subject"] = f"WebTest {payload['suite']} success={payload.get('success', payload['failed'] == 0)} failed={payload['failed']}"
        message["From"] = self.sender
        message["To"] = ", ".join(self.receivers)
        message.set_content(str(payload))
        with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout) as client:
            client.login(self.username, self.password)
            refused = client.send_message(message)
        if refused:
            raise _PartialEmailDeliveryError(refused)


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

    def send(self, result: SuiteResult, *, statistics: dict,
             redactor: Redactor | None = None) -> list[str]:
        errors: list[str] = []
        redactor = redactor or Redactor()
        for channel in self.channels:
            if isinstance(channel.sender, EmailSender):
                redactor.add(channel.sender.password)
            elif isinstance(channel.sender, (WebhookSender, DingtalkSender, FeishuSender)):
                redactor.collect(channel.sender.url)
        statistics = safe_statistics(result, statistics, redactor=redactor)
        safe_result = redactor.redact_result(result)
        payload = {
            "suite": safe_result.name,
            "total": result.total_cases,
            "passed": result.passed_cases,
            "failed": result.failed_cases,
            "blocked": result.blocked_cases,
            "success": result.passed,
            "error_message": safe_result.error_message or next((step.error_message for item in safe_result.suite_results or [safe_result]
                for step in item.setup_steps + item.teardown_steps if not step.passed), None),
            "statistics": statistics,
        }
        for channel in self.channels:
            if not channel.enabled or not _should_send(channel.trigger, result):
                continue
            if channel.sender is None:
                errors.append(f"{channel.type}: enabled channel has no sender")
                continue
            for attempt in range(channel.retries + 1):
                try:
                    channel.sender.send(deepcopy(payload))
                    break
                except Exception as exc:
                    if isinstance(exc, _PartialEmailDeliveryError) or attempt >= channel.retries:
                        errors.append(redactor.redact(f"{channel.type}: {exc}"))
                        break
        return redactor.redact(errors)


def _should_send(trigger: str, result: SuiteResult) -> bool:
    if trigger == "always":
        return True
    if trigger == "on_failure":
        return not result.passed
    if trigger == "on_success":
        return result.passed
    return False


def _notification_title(payload: dict) -> str:
    return f"WebTest 测试结果：{payload['suite']}"


def _markdown_summary(payload: dict) -> str:
    return (
        f"### {_notification_title(payload)}\n\n"
        f"- 状态：{'通过' if payload.get('success', payload['failed'] == 0) else '失败'}\n"
        f"- 总数：{payload['total']}\n"
        f"- 通过：{payload['passed']}\n"
        f"- 失败：{payload['failed']}\n"
        f"- 未执行：{payload.get('blocked', 0)}\n"
        f"{payload.get('error_message') or ''}"
    )


def _plain_summary(payload: dict) -> str:
    return f"状态：{'通过' if payload.get('success', payload['failed'] == 0) else '失败'}，总数：{payload['total']}，通过：{payload['passed']}，失败：{payload['failed']}，未执行：{payload.get('blocked', 0)}。{payload.get('error_message') or ''}"


def _check_bot_response(response, code_key):
    if response is None:  # 支持不返回正文的自定义客户端。
        return
    payload = json.loads(response)
    code = payload.get(code_key)
    if code != 0:
        raise RuntimeError(f"Robot rejected notification: {payload}")
