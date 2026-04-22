"""Notification adapters for external channels."""

from .dingtalk_notifier import DingTalkNotifier
from .dispatcher import NotificationDispatcher, build_notification_summary
from .email_notifier import EmailNotifier, SmtpConfig
from .webhook_notifier import WebhookNotifier

__all__ = [
    "DingTalkNotifier",
    "EmailNotifier",
    "NotificationDispatcher",
    "SmtpConfig",
    "WebhookNotifier",
    "build_notification_summary",
]
