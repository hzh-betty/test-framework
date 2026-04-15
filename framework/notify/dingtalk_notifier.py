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


class DingTalkNotifier:
    def __init__(self, webhook: str, sender: Sender | None = None, retries: int = 0):
        self.webhook = webhook
        self.sender = sender or _default_sender
        self.retries = retries

    def send(self, title: str, text: str) -> None:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text,
            },
        }
        status_code = 500
        for _ in range(self.retries + 1):
            try:
                status_code = self.sender(self.webhook, payload)
            except Exception:
                status_code = 500
                continue
            if status_code < 400:
                return
        raise RuntimeError(f"DingTalk webhook returned status code {status_code}.")
