from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from email.message import Message

import pytest
from pydantic import ValidationError

import webtest_core.browser.actions as browser
import webtest_core.keywords.http as http
from webtest_core import __version__
from webtest_core.browser import BrowserActions
from webtest_core.dsl import CaseSpec, DslValidationError, RuntimeConfig, StepSpec, SuiteSpec, interpolate, load_runtime_config
from webtest_core.dsl.durations import seconds
from webtest_core.keywords import KeywordRegistry
from webtest_core.keywords.http import HttpKeywordLibrary, UrllibHttpClient
from webtest_core.keywords.web import WebKeywordLibrary
from webtest_core.runtime import select_cases


@pytest.mark.parametrize("value, expected", [("500ms", 0.5), ("2s", 2), ("1 minute", 60), ("2 minutes", 120), ("3 min", 180), (2, 2)])
def test_durations_are_shared_and_parse_plural_units(value, expected):
    assert seconds(value) == expected


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True, "bogus", "-1s"])
def test_invalid_durations_are_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        seconds(value)


def test_whole_variable_reference_preserves_types_and_copies_mutables():
    variables = {"n": 200, "flag": True, "obj": {"roles": ["admin"]}}
    assert interpolate(["${n}", "${flag}", "code=${n}"], variables) == [200, True, "code=200"]
    payload = interpolate("${obj}", variables)
    payload["roles"].append("editor")
    assert variables["obj"]["roles"] == ["admin"]
    with pytest.raises(DslValidationError, match="Undefined variable"):
        interpolate("${missing}", variables)


@pytest.mark.parametrize("config", [{"headles": True}, {"timeouts": {"explicit_wait": -1}},
    {"notifications": {"channels": [{"type": "email"}]}},
    {"notifications": {"channels": [{"type": "webhook", "webhook": "https://local.test", "retries": -1}]}},
    {"notifications": {"channels": [{"type": "wechat", "enabled": False}]}},
    {"notifications": {"channels": [{"type": "dingtalk", "webhook": "https://local.test", "smtp": {}}]}}])
def test_runtime_configuration_rejects_invalid_or_unimplemented_fields(config):
    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate(config)


def test_missing_environment_variable_only_allowed_for_disabled_channel(tmp_path, monkeypatch):
    monkeypatch.delenv("WEBTEST_MISSING", raising=False)
    config = tmp_path / "config.yaml"
    config.write_text("notifications:\n  channels:\n    - type: webhook\n      enabled: false\n      webhook: ${WEBTEST_MISSING}\n", encoding="utf-8")
    assert load_runtime_config(config).notifications.channels[0].webhook == ""
    config.write_text(config.read_text(encoding="utf-8").replace("false", "true"), encoding="utf-8")
    with pytest.raises(DslValidationError, match="config.notifications.channels.0.webhook.*WEBTEST_MISSING"):
        load_runtime_config(config)


def test_duplicate_case_names_rejected_and_tags_normalized():
    with pytest.raises(ValidationError, match="unique"):
        SuiteSpec(name="Duplicate", cases=[CaseSpec(name="same"), CaseSpec(name="same")])
    assert CaseSpec(name="case", tags=["Smoke", "smoke", " smoke "]).tags == ["smoke"]


@pytest.mark.parametrize("expression", ["slow AND", "(slow", "slow slow", "", "slow OR )"])
def test_invalid_filters_fail_even_with_zero_cases(expression):
    with pytest.raises(DslValidationError):
        select_cases([], exclude_tag_expr=expression)


def test_tag_precedence_parentheses_and_not():
    cases = [CaseSpec(name="a", tags=["smoke"]), CaseSpec(name="b", tags=["slow", "api"]), CaseSpec(name="c", tags=["slow"])]
    assert [case.name for case in select_cases(cases, include_tag_expr="smoke OR slow AND api")] == ["a", "b"]
    assert [case.name for case in select_cases(cases, include_tag_expr="(smoke OR slow) AND NOT api")] == ["a", "c"]


def test_numeric_frame_and_window_indexes_and_screenshot_failure(tmp_path):
    calls = []
    driver = SimpleNamespace(switch_to=SimpleNamespace(frame=lambda index: calls.append(("frame", index)),
        window=lambda handle: calls.append(("window", handle))), window_handles=["first", "second"], save_screenshot=lambda path: False)
    registry = KeywordRegistry.from_libraries([WebKeywordLibrary(BrowserActions(driver))])
    registry.run("Switch Frame", [0])
    registry.run("Switch Window", [1])
    assert calls == [("frame", 0), ("window", "second")]
    with pytest.raises(DslValidationError):
        registry.run("Switch Frame", [True])
    with pytest.raises(RuntimeError, match="Screenshot"):
        registry.run("Screenshot", [str(tmp_path / "nested" / "shot.png")])
    assert (tmp_path / "nested").is_dir()


def test_explicit_wait_suspends_implicit_wait_and_restores_after_error(monkeypatch):
    calls = []
    driver = SimpleNamespace(implicitly_wait=lambda timeout: calls.append(timeout))
    actions = BrowserActions(driver, implicit_wait=5)

    class Wait:
        def __init__(self, driver, timeout):
            assert calls == [0] and timeout == 0.5

        def until(self, condition):
            raise RuntimeError("wait failed")

    monkeypatch.setattr(browser, "WebDriverWait", Wait)
    with pytest.raises(RuntimeError, match="wait failed"):
        actions.wait_url_contains("dashboard", 0.5)
    assert calls == [0, 5]


def test_web_registry_validates_locator_and_uses_configured_timeout():
    calls = []
    actions = SimpleNamespace(wait_visible=lambda locator, timeout: calls.append(timeout))
    registry = KeywordRegistry.from_libraries([WebKeywordLibrary(actions, default_timeout=1)])
    registry.run("Wait Visible", ["id=panel"])
    assert calls == [1]
    with pytest.raises(DslValidationError, match="Unknown locator"):
        registry.bind("Wait Visible", ["bad=panel"], {})


@pytest.fixture
def local_http():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            status = 404 if self.path == "/missing" else 200
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"name": "中文", "status": status}, ensure_ascii=False).encode("utf-8"))

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(201)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_urllib_requests_handle_error_response_and_typed_json(local_http):
    client = UrllibHttpClient()
    response = client.request("GET", local_http + "/missing", timeout="500ms")
    assert response.status_code == 404 and response.json()["name"] == "中文"
    response = client.request("POST", local_http, json={"enabled": True, "count": 2}, timeout="2 seconds")
    assert response.status_code == 201 and response.json() == {"enabled": True, "count": 2}
    registry = KeywordRegistry.from_libraries([HttpKeywordLibrary(client)])
    with pytest.raises(DslValidationError, match="Unknown HTTP options"):
        registry.run("HTTP GET", [local_http], {"timout": 1})


def test_http_error_body_is_closed(monkeypatch):
    body = io.BytesIO(b"missing")
    headers = Message()
    error = HTTPError("http://local.test", 404, "missing", headers, body)
    monkeypatch.setattr(http.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    assert UrllibHttpClient().request("GET", "http://local.test").body == "missing"
    assert body.closed


def test_runtime_version_matches_installed_package():
    from importlib.metadata import version
    assert __version__ == version("webtest-core")


def test_variable_cycles_and_nested_missing_references_fail():
    assert interpolate("${url}", {"url": "${base}/login", "base": "https://local.test"}) == "https://local.test/login"
    with pytest.raises(DslValidationError, match="cycle"):
        interpolate("${a}", {"a": "${b}", "b": "${a}"})
    with pytest.raises(DslValidationError, match="Undefined"):
        interpolate("${a}", {"a": "${missing}"})


def test_disabled_channel_enabled_from_environment_allows_missing_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBTEST_ENABLED", "false")
    monkeypatch.delenv("WEBTEST_ABSENT_URL", raising=False)
    path = tmp_path / "config.yaml"
    path.write_text("notifications:\n  channels:\n    - type: webhook\n      enabled: ${WEBTEST_ENABLED}\n      webhook: ${WEBTEST_ABSENT_URL}\n", encoding="utf-8")
    assert load_runtime_config(path).notifications.channels[0].enabled is False


def test_boolean_step_timeout_and_non_mapping_config_are_rejected(tmp_path):
    with pytest.raises(ValidationError):
        StepSpec(keyword="Wait Visible", timeout=True)
    path = tmp_path / "config.yaml"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(DslValidationError, match="mapping"):
        load_runtime_config(path)
