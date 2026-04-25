import pytest

from webtest_core.keywords import KeywordRegistry
from webtest_core.keywords.http import HttpKeywordLibrary, HttpResponse


class FakeHttpClient:
    def __init__(self):
        self.calls = []
        self.response = HttpResponse(
            status_code=200,
            headers={"content-type": "application/json", "x-trace-id": "abc"},
            body='{"data": {"user": {"name": "Alice", "roles": ["admin"]}}, "ok": true}',
        )

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_http_keywords_request_and_assert_response_fields():
    client = FakeHttpClient()
    registry = KeywordRegistry.from_libraries([HttpKeywordLibrary(client=client)])

    registry.run(
        "HTTP GET",
        ["https://api.example.test/users/1"],
        {"headers": {"Authorization": "Bearer token"}, "timeout": 3},
    )
    registry.run("Assert Response Status", [200])
    registry.run("Assert Response Header", ["content-type", "application/json"])
    registry.run("Assert Response JSON", ["data.user.name", "Alice"])
    registry.run("Assert Response JSON", ["data.user.roles.0", "admin"])
    registry.run("Assert Response Body Contains", ["Alice"])

    assert client.calls == [
        (
            "GET",
            "https://api.example.test/users/1",
            {"headers": {"Authorization": "Bearer token"}, "timeout": 3},
        )
    ]


def test_http_keywords_post_json_body_and_report_clear_assertion_error():
    client = FakeHttpClient()
    registry = KeywordRegistry.from_libraries([HttpKeywordLibrary(client=client)])

    registry.run("HTTP POST", ["https://api.example.test/users"], {"json": {"name": "Alice"}})

    assert client.calls[0] == (
        "POST",
        "https://api.example.test/users",
        {"json": {"name": "Alice"}},
    )
    with pytest.raises(AssertionError, match="响应 JSON 字段断言失败"):
        registry.run("Assert Response JSON", ["data.user.name", "Bob"])


def test_http_assertions_require_a_previous_response():
    registry = KeywordRegistry.from_libraries([HttpKeywordLibrary(client=FakeHttpClient())])

    with pytest.raises(AssertionError, match="还没有 HTTP 响应"):
        registry.run("Assert Response Status", [200])
