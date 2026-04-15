from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
from typing import Callable, Sequence


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    receivers: list[str]
    use_ssl: bool = True
    timeout_seconds: int = 10
    retries: int = 0


SmtpFactory = Callable[[SmtpConfig], object]


def _default_smtp_factory(config: SmtpConfig):
    if config.use_ssl:
        return smtplib.SMTP_SSL(config.host, config.port, timeout=config.timeout_seconds)
    return smtplib.SMTP(config.host, config.port, timeout=config.timeout_seconds)


class EmailNotifier:
    def __init__(self, config: SmtpConfig, smtp_factory: SmtpFactory | None = None):
        self.config = config
        self.smtp_factory = smtp_factory or _default_smtp_factory

    def send(
        self,
        subject: str,
        body: str,
        attachment_paths: Sequence[str] | None = None,
    ) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.sender
        message["To"] = ", ".join(self.config.receivers)
        message.set_content(body)

        for attachment_path in attachment_paths or []:
            with open(attachment_path, "rb") as handle:
                payload = handle.read()
            filename = attachment_path.split("/")[-1]
            message.add_attachment(
                payload,
                maintype="application",
                subtype="octet-stream",
                filename=filename,
            )

        last_error: Exception | None = None
        for _ in range(self.config.retries + 1):
            client = None
            try:
                client = self.smtp_factory(self.config)
                client.login(self.config.username, self.config.password)
                client.send_message(message)
                try:
                    client.quit()
                except Exception:
                    pass
                return
            except Exception as exc:
                last_error = exc
                if client is not None:
                    try:
                        client.quit()
                    except Exception:
                        pass
        raise RuntimeError(f"Email notification failed: {last_error}")
