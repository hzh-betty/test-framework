"""执行保留原值；诊断与产物只使用脱敏副本。"""

import re
import json
from dataclasses import asdict, fields, is_dataclass, replace
from html import escape
from urllib.parse import parse_qsl, quote, quote_plus, unquote, urlencode, urlsplit, urlunsplit


_URL = re.compile(r"https?://[^\s<>\"']+", re.I)


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
        elif value is not None and not isinstance(value, str):
            self.add(str(value))

    def collect_suite(self, payload: dict) -> None:
        """按变量作用域收集 DSL 秘密，附件也使用与执行相同的插值规则。"""
        from webtest_core.dsl.errors import DslValidationError
        from webtest_core.dsl.variables import interpolate

        self.collect(payload)
        suite = payload.get("suite", payload)
        if not isinstance(suite, dict):
            return

        def resolve(value, variables):
            if isinstance(value, list):
                return [resolve(item, variables) for item in value]
            if isinstance(value, dict):
                return {key: resolve(item, variables) for key, item in value.items()}
            try:
                return interpolate(value, variables)
            except DslValidationError:
                return value

        variables = suite.get("variables", {})
        self.collect(resolve(variables, variables))
        definitions = [step for steps in suite.get("keywords", {}).values() for step in steps]
        self.collect(resolve(suite.get("setup", []) + suite.get("teardown", []) + definitions, variables))
        for case in suite.get("cases", []):
            scoped = {**variables, **case.get("variables", {})}
            self.collect(resolve(scoped, scoped))
            steps = case.get("setup", []) + case.get("steps", []) + case.get("teardown", []) + definitions
            self.collect(resolve(steps, scoped))

    def redact_suite(self, payload: dict) -> dict:
        self.collect_suite(payload)
        safe = self.redact(payload)

        def visit(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"variables", "args", "kwargs"}:
                        value[key] = self.redact_values(item)
                    else:
                        visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(safe)
        return safe

    def redact_values(self, value):
        """参数可含数字秘密；计数、时间等系统字段不使用此入口。"""
        if isinstance(value, dict):
            return {key: "***" if sensitive_key(str(key)) else self.redact_values(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_values(item) for item in value]
        if value is not None and not isinstance(value, str) and str(value) in self.secrets:
            return "***"
        return self.redact(value)

    def redact_result(self, result):
        """脱敏结果副本，保留 dataclass 结构及统计所用的数值。"""
        from webtest_core.runtime.models import identify_result

        result = identify_result(result)
        self.collect(asdict(result))

        def copy(value):
            if is_dataclass(value):
                return replace(value, **{
                    field.name: getattr(value, field.name) if field.name in {"failure_type", "suite_id", "case_id"}
                    else self.redact_values(getattr(value, field.name)) if field.name in {"arguments", "kwargs"}
                    else copy(getattr(value, field.name)) for field in fields(value)
                })
            if isinstance(value, list):
                return [copy(item) for item in value]
            if isinstance(value, dict):
                return {key: item if key == "failure_type" else "***" if sensitive_key(str(key))
                        else copy(item) for key, item in value.items()}
            return self.redact(value)

        return copy(result)

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
        elif isinstance(value, str):
            for match in _URL.finditer(value):
                try:
                    parts = urlsplit(match.group())
                    if parts.password is not None:
                        self.add(unquote(parts.password))
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
            def redact_url(match):
                url = match.group()
                try:
                    parts = urlsplit(url)
                    if parts.username is not None:
                        parts = parts._replace(netloc="***@" + parts.netloc.rsplit("@", 1)[1])
                    query = parse_qsl(parts.query, keep_blank_values=True)
                    if any(sensitive_key(key) or item in self.secrets for key, item in query):
                        parts = parts._replace(query=urlencode([(key, "***" if sensitive_key(key) or item in self.secrets else item) for key, item in query]))
                    return urlunsplit(parts)
                except ValueError:
                    return url

            value = _URL.sub(redact_url, value)
            for secret in sorted(self.secrets, key=len, reverse=True):
                for spelling in sorted({secret, escape(secret), quote(secret, safe=""), quote_plus(secret, safe=""), json.dumps(secret, ensure_ascii=False)[1:-1], json.dumps(secret)[1:-1], repr(secret)[1:-1]}, key=len, reverse=True):
                    if "%" not in spelling:
                        value = value.replace(spelling, "***")
                        continue
                    pattern = "".join(
                        "(?i:" + re.escape(part) + ")" if re.fullmatch(r"%[0-9A-Fa-f]{2}", part)
                        else re.escape(part) for part in re.split(r"(%[0-9A-Fa-f]{2})", spelling)
                    )
                    value = re.sub(pattern, "***", value)
        return value
