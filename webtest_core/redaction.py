"""执行保留原值；诊断与产物只使用脱敏副本。"""

import re
import json
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def sensitive_key(key: str) -> bool:
    name = re.sub(r"[^a-z0-9]", "", key.casefold())
    return any(part in name for part in ("password", "passwd", "secret", "token", "apikey", "authorization", "cookie", "accesskey"))


class Redactor:
    def __init__(self, *values: object):
        self.secrets: set[str] = set()
        for value in values:
            self.collect(value)

    def add(self, value: object) -> None:
        if isinstance(value, str) and value:
            self.secrets.add(value)
            if value.lower().startswith("bearer "):
                self.secrets.add(value[7:])
        elif isinstance(value, (dict, list)):
            for item in (value.values() if isinstance(value, dict) else value):
                self.add(item)

    def collect(self, value: object) -> None:
        if isinstance(value, dict):
            args = value.get("args", value.get("arguments", []))
            if isinstance(args, list):
                for index in value.get("sensitive_args", []):
                    if isinstance(index, int) and 0 <= index < len(args):
                        self.add(args[index])
                if re.sub(r"[\s_-]+", " ", str(value.get("keyword", "")).strip().casefold()) == "type text":
                    kwargs = value.get("kwargs", {})
                    locator = args[0] if args else kwargs.get("locator", "")
                    if sensitive_key(str(locator)):
                        self.add(args[1] if len(args) > 1 else kwargs.get("text"))
            for key, item in value.items():
                if sensitive_key(str(key)):
                    self.add(item)
                self.collect(item)
        elif isinstance(value, list):
            for item in value:
                self.collect(item)
        elif isinstance(value, str) and value.startswith(("https://", "http://")):
            try:
                parts = urlsplit(value)
                self.add(parts.password)
                for key, item in parse_qsl(parts.query):
                    if sensitive_key(key):
                        self.add(item)
            except ValueError:
                pass

    def redact(self, value: object) -> object:
        if isinstance(value, dict):
            return {key: "***" if sensitive_key(str(key)) else self.redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            if value.startswith(("https://", "http://")):
                try:
                    parts = urlsplit(value)
                    if parts.username is not None:
                        value = urlunsplit(parts._replace(netloc="***@" + parts.netloc.rsplit("@", 1)[1]))
                    query = parse_qsl(parts.query, keep_blank_values=True)
                    if any(sensitive_key(key) for key, _ in query):
                        value = urlunsplit(urlsplit(value)._replace(query=urlencode([(key, "***" if sensitive_key(key) else item) for key, item in query])))
                except ValueError:
                    pass
            for secret in sorted(self.secrets, key=len, reverse=True):
                for spelling in sorted({secret, escape(secret), json.dumps(secret, ensure_ascii=False)[1:-1], json.dumps(secret)[1:-1], repr(secret)[1:-1]}, key=len, reverse=True):
                    value = value.replace(spelling, "***")
        return value
