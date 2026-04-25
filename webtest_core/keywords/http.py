"""HTTP/API 测试关键字。

这个模块给 YAML DSL 增加接口测试能力。关键字库会保存最近一次 HTTP 响应，
后续断言关键字都基于这份响应执行。这样用例可以写成“请求一步、断言多步”，
和常见 API 测试阅读方式一致。
"""

from __future__ import annotations

from dataclasses import dataclass
import json as json_module
from typing import Protocol
from urllib import error, request

from webtest_core.keywords import keyword


@dataclass(frozen=True)
class HttpResponse:
    """HTTP 响应的最小稳定表示。"""

    status_code: int
    headers: dict[str, str]
    body: str

    def json(self) -> object:
        return json_module.loads(self.body)


class HttpClient(Protocol):
    def request(self, method: str, url: str, **kwargs) -> HttpResponse:
        ...


class UrllibHttpClient:
    """基于标准库 urllib 的 HTTP 客户端，避免为基础能力引入额外依赖。"""

    def request(self, method: str, url: str, **kwargs) -> HttpResponse:
        headers = dict(kwargs.get("headers") or {})
        timeout = kwargs.get("timeout", 10)
        data = kwargs.get("data")
        json_payload = kwargs.get("json")
        if json_payload is not None:
            data = json_module.dumps(json_payload, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(data, str):
            data = data.encode("utf-8")

        req = request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode(_charset(response.headers.get("content-type")))
                return HttpResponse(
                    status_code=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=body,
                )
        except error.HTTPError as exc:
            body = exc.read().decode(_charset(exc.headers.get("content-type")))
            return HttpResponse(
                status_code=exc.code,
                headers={key.lower(): value for key, value in exc.headers.items()},
                body=body,
            )


class HttpKeywordLibrary:
    """HTTP 请求和响应断言关键字库。"""

    def __init__(self, client: HttpClient | None = None):
        self.client = client or UrllibHttpClient()
        self.last_response: HttpResponse | None = None

    @keyword("HTTP Request")
    def http_request(self, method: str, url: str, **kwargs):
        self.last_response = self.client.request(method.upper(), url, **kwargs)

    @keyword("HTTP GET")
    def http_get(self, url: str, **kwargs):
        self.http_request("GET", url, **kwargs)

    @keyword("HTTP POST")
    def http_post(self, url: str, **kwargs):
        self.http_request("POST", url, **kwargs)

    @keyword("HTTP PUT")
    def http_put(self, url: str, **kwargs):
        self.http_request("PUT", url, **kwargs)

    @keyword("HTTP PATCH")
    def http_patch(self, url: str, **kwargs):
        self.http_request("PATCH", url, **kwargs)

    @keyword("HTTP DELETE")
    def http_delete(self, url: str, **kwargs):
        self.http_request("DELETE", url, **kwargs)

    @keyword("Assert Response Status")
    def assert_response_status(self, expected_status: int):
        response = self._response()
        if response.status_code != int(expected_status):
            raise AssertionError(
                f"响应状态码断言失败：期望 {expected_status}，实际 {response.status_code}"
            )

    @keyword("Assert Response Header")
    def assert_response_header(self, name: str, expected_value: str):
        response = self._response()
        actual = response.headers.get(name.lower())
        if actual != expected_value:
            raise AssertionError(
                f"响应 Header 断言失败：{name} 期望 {expected_value!r}，实际 {actual!r}"
            )

    @keyword("Assert Response JSON")
    def assert_response_json(self, path: str, expected_value: object):
        response = self._response()
        actual = _read_json_path(response.json(), path)
        if actual != expected_value:
            raise AssertionError(
                f"响应 JSON 字段断言失败：{path} 期望 {expected_value!r}，实际 {actual!r}"
            )

    @keyword("Assert Response Body Contains")
    def assert_response_body_contains(self, expected_text: str):
        response = self._response()
        if expected_text not in response.body:
            raise AssertionError(f"响应正文不包含期望文本：{expected_text!r}")

    def _response(self) -> HttpResponse:
        if self.last_response is None:
            raise AssertionError("还没有 HTTP 响应，请先执行 HTTP 请求关键字。")
        return self.last_response


def _read_json_path(payload: object, path: str) -> object:
    current = payload
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(f"路径 {path} 在 {part} 处无法继续读取")
    return current


def _charset(content_type: str | None) -> str:
    if not content_type:
        return "utf-8"
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1]
    return "utf-8"
