from __future__ import annotations

import json
from typing import Callable
from urllib import request


Sender = Callable[[str, dict], int]


def _default_sender(webhook: str, payload: dict) -> int:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        return response.status


class WebhookNotifier:
    def __init__(
        self,
        kind: str,
        webhook: str,
        sender: Sender | None = None,
        retries: int = 0,
    ):
        self.kind = kind.strip().lower()
        self.webhook = webhook
        self.sender = sender or _default_sender
        self.retries = retries

    def send(self, title: str, text: str) -> None:
        payload = self._payload(title=title, text=text)
        status_code = 500
        for _ in range(self.retries + 1):
            try:
                status_code = self.sender(self.webhook, payload)
            except Exception:
                status_code = 500
                continue
            if status_code < 400:
                return
        raise RuntimeError(f"{self.kind} webhook returned status code {status_code}.")

    def _payload(self, title: str, text: str) -> dict:
        if self.kind == "dingtalk":
            return {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": text},
            }
        if self.kind == "wecom":
            return {
                "msgtype": "markdown",
                "markdown": {"content": f"## {title}\n{text}"},
            }
        if self.kind == "feishu":
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                    },
                    "elements": [
                        {"tag": "markdown", "content": text},
                    ],
                },
            }
        raise ValueError(f"Unsupported webhook notifier kind: {self.kind}")
