from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import subprocess
from threading import Thread
from types import SimpleNamespace

import pytest

from webtest_core.browser import BrowserActions, Locator, parse_locator
from webtest_core.dsl import DslValidationError
from webtest_core.keywords import KeywordRegistry
import webtest_core.keywords.http as http
from webtest_core.keywords.http import HttpKeywordLibrary, HttpResponse, UrllibHttpClient
from webtest_core.keywords.web import WebKeywordLibrary


@pytest.mark.parametrize("selector", [
    "input[name=username]", "[data-state=ready]",
    "a[href='https://example.test/?a=b']", "button:not([disabled=true])",
])
def test_default_css_accepts_attribute_equals(selector):
    assert parse_locator(selector) == Locator("css selector", selector)


@pytest.mark.parametrize("locator, markup, expected", [
    ("text=Login", '<html><body><div><button id="target">Login</button></div></body></html>', ["target"]),
    ("partial_text=Login", '<html><body><div><button id="target">Login now</button></div></body></html>', ["target"]),
    ("text=Log in", '<html><body><button id="mixed">Log <span>in</span></button></body></html>', ["mixed"]),
    ("text=Login", '<html><body><button id="hidden" style="display:none">Login</button></body></html>', ["hidden"]),
    ('text=He said "don\'t"', '<html><body><button id="quoted">He said "don\'t"</button></body></html>', ["quoted"]),
])
def test_text_locator_selects_innermost_matching_dom_nodes(locator, markup, expected):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell/.NET XPath evaluator is not available")
    script = """
$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
$document = [System.Xml.XmlDocument]::new()
$document.LoadXml($payload.markup)
$ids = @($document.SelectNodes($payload.xpath) | ForEach-Object { $_.GetAttribute('id') })
ConvertTo-Json -InputObject $ids -Compress
"""
    result = subprocess.run(
        [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        input=json.dumps({"markup": markup, "xpath": parse_locator(locator).value}),
        capture_output=True, text=True, timeout=10, check=True,
    )
    assert json.loads(result.stdout) == expected


@pytest.mark.parametrize("actual, expected", [
    (True, 1), (False, 0), (1, True), (0, False),
    ({"enabled": True}, {"enabled": 1}), ([False], [0]),
    ({"items": [{"flags": [True]}]}, {"items": [{"flags": [1]}]}),
])
def test_json_assertions_distinguish_booleans_from_numbers_recursively(actual, expected):
    library = HttpKeywordLibrary()
    library.last_response = HttpResponse(200, {}, json.dumps({"value": actual}))
    with pytest.raises(AssertionError, match="响应 JSON 字段断言失败"):
        library.assert_response_json("value", expected)


def test_json_assertions_treat_integer_and_float_as_json_numbers():
    library = HttpKeywordLibrary()
    library.last_response = HttpResponse(200, {}, '{"value":{"items":[1,true,0]}}')
    library.assert_response_json("value", {"items": [1.0, True, 0.0]})


@pytest.mark.parametrize("keyword_name, action_name", [
    ("Switch Frame", "switch_frame"), ("Switch Window", "switch_window"),
])
@pytest.mark.parametrize("target", ["-1", -1, True])
def test_frame_and_window_targets_have_identical_precheck_and_runtime_validation(keyword_name, action_name, target):
    actions = BrowserActions(SimpleNamespace())
    registry = KeywordRegistry.from_libraries([WebKeywordLibrary(actions)])
    with pytest.raises(DslValidationError, match="non-negative"):
        registry.bind(keyword_name, [target], {})
    with pytest.raises(DslValidationError, match="non-negative"):
        registry.run(keyword_name, [target])
    with pytest.raises(ValueError, match="non-negative"):
        getattr(actions, action_name)(target)


@pytest.fixture
def http_sink():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.headers.get("Content-Type"), body))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("header", ["Content-Type", "content-type", "CONTENT-TYPE"])
def test_urllib_preserves_custom_content_type_on_the_wire(http_sink, header):
    url, received = http_sink
    response = UrllibHttpClient().request(
        "POST", url, headers={header: "application/merge-patch+json"}, json={"enabled": True},
    )
    assert response.status_code == 200
    assert received == [("application/merge-patch+json", b'{"enabled": true}')]


def test_urllib_defaults_json_content_type_on_the_wire(http_sink):
    url, received = http_sink
    UrllibHttpClient().request("POST", url, json={"count": 1})
    assert received == [("application/json", b'{"count": 1}')]


@pytest.mark.parametrize("timeout", [0, 0.0, "0", "0ms"])
def test_http_rejects_zero_timeout_at_precheck_and_direct_client_boundaries(timeout, monkeypatch):
    monkeypatch.setattr(http.request, "urlopen", lambda *args, **kwargs: pytest.fail("invalid timeout reached I/O"))
    registry = KeywordRegistry.from_libraries([HttpKeywordLibrary()])
    with pytest.raises(DslValidationError, match="greater than zero"):
        registry.bind("HTTP GET", ["http://local.test"], {"timeout": timeout})
    with pytest.raises(ValueError, match="greater than zero"):
        UrllibHttpClient().request("GET", "http://local.test", timeout=timeout)
    browser_registry = KeywordRegistry.from_libraries([WebKeywordLibrary(SimpleNamespace())])
    assert browser_registry.bind("Wait Visible", ["id=panel"], {"timeout": timeout}).arguments["timeout"] == 0


@pytest.mark.parametrize("options", [
    {"json": {"value": float("nan")}}, {"json": {"value": {1, 2}}},
    {"data": "text", "json": {}}, {"headers": ["content-type"]},
])
def test_direct_urllib_and_precheck_reject_invalid_options_before_io(options, monkeypatch):
    monkeypatch.setattr(http.request, "urlopen", lambda *args, **kwargs: pytest.fail("invalid request reached I/O"))
    with pytest.raises((TypeError, ValueError)):
        UrllibHttpClient().request("POST", "http://local.test", **options)
    registry = KeywordRegistry.from_libraries([HttpKeywordLibrary()])
    with pytest.raises(DslValidationError):
        registry.bind("HTTP POST", ["http://local.test"], options)


def test_direct_library_still_validates_options_with_custom_client():
    client = SimpleNamespace(request=lambda *args, **kwargs: pytest.fail("invalid options reached client"))
    with pytest.raises(ValueError, match="Unknown HTTP options"):
        HttpKeywordLibrary(client).http_post("http://local.test", timout=1)
    with pytest.raises(ValueError, match="greater than zero"):
        HttpKeywordLibrary(client).http_post("http://local.test", timeout=0)


@pytest.mark.parametrize("through_registry, expected_calls", [(True, 2), (False, 1)])
def test_json_serialization_is_only_for_precheck_and_sending(http_sink, monkeypatch, through_registry, expected_calls):
    url, received = http_sink
    payload = {"nested": {"values": [True, 1, "中文"]}}
    original_dumps = http.json_module.dumps
    calls = []

    def count_dumps(value, **kwargs):
        if value is payload:
            calls.append(kwargs)
        return original_dumps(value, **kwargs)

    monkeypatch.setattr(http.json_module, "dumps", count_dumps)
    if through_registry:
        registry = KeywordRegistry.from_libraries([HttpKeywordLibrary()])
        registry.run("HTTP POST", [url], {"json": payload})
    else:
        UrllibHttpClient().request("POST", url, json=payload)
    assert len(calls) == expected_calls
    assert json.loads(received[0][1]) == payload
