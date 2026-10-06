from collections import Counter
import json
from pathlib import Path
import re
import struct
from threading import Barrier, Event
import time
import zlib

import pytest
import yaml

from webtest_core import cli
from webtest_core.keywords import KeywordRegistry
from webtest_core.keywords.http import HttpKeywordLibrary


def latest(root):
    return Path(json.loads((root / "latest-run.json").read_text(encoding="utf-8"))["directory"])


def write_suite(directory, content):
    path = directory / "suite.yaml"
    path.write_text(yaml.safe_dump({"suite": content}), encoding="utf-8")
    return path


def png_bytes(red):
    def chunk(name, payload):
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes([0, red, 0, 0, 255]))) + chunk(b"IEND", b""))


def assert_screenshot_reports(directory, result, sources):
    cases = result["cases"]
    expected_images = Counter(source.read_bytes() for source in sources)
    html_dir = directory / "html-report"
    html = (html_dir / "index.html").read_text(encoding="utf-8")
    links = set(re.findall(r'href="(attachments/[^\"]+\.png)"', html))
    assert len(links) == len(sources)
    assert Counter((html_dir / link).read_bytes() for link in links) == expected_images

    allure_dir = directory / "allure-results"
    assert Counter(image.read_bytes() for image in allure_dir.glob("*.png")) == expected_images
    containers = [json.loads(path.read_text(encoding="utf-8")) for path in allure_dir.glob("*-container.json")]
    assert len(containers) == 1
    assert containers[0]["start"] == result["start"]
    assert containers[0]["stop"] == result["stop"]
    exported = {item["name"]: item for path in allure_dir.glob("*-result.json")
                if (item := json.loads(path.read_text(encoding="utf-8")))["name"] in {case["name"] for case in cases}}
    assert set(exported) == {case["name"] for case in cases}
    for case in cases:
        allure_case = exported[case["name"]]
        assert allure_case["start"] == case["start"]
        assert allure_case["stop"] == case["stop"]
        assert len(allure_case["steps"]) == len(case["steps"])
        for exported_step, step in zip(allure_case["steps"], case["steps"]):
            assert exported_step["start"] == step["start"]
            assert exported_step["stop"] == step["stop"]
            assert case["start"] <= step["start"] <= step["stop"] <= case["stop"]
            for attachment in exported_step["attachments"]:
                assert (allure_dir / attachment["source"]).read_bytes() in expected_images
        diagnostics = next(item for item in allure_case["attachments"] if item["name"] == "diagnostics.json")
        history = json.loads((allure_dir / diagnostics["source"]).read_text(encoding="utf-8"))
        for attempt in history["attempts"]:
            assert case["start"] <= attempt["start"] <= attempt["stop"] <= case["stop"]
            for step in attempt["steps"]:
                for attachment in step["attachments"]:
                    assert (allure_dir / attachment["source"]).read_bytes() in expected_images


@pytest.mark.parametrize("encoded", ["PRIVATE%2BURL%20TOKEN", "PRIVATE%2bURL+TOKEN", "PRIVATE%252BURL%2520TOKEN"])
def test_embedded_url_credentials_are_removed_from_every_cli_output(tmp_path, monkeypatch, encoded):
    url = f"https://local.test/api?api_token={encoded}"
    received = []
    class Client:
        def request(self, method, actual_url, **kwargs):
            received.append(actual_url)
            raise RuntimeError("request failed for " + actual_url)
    monkeypatch.setattr(cli, "_build_registry", lambda *args: KeywordRegistry.from_libraries([HttpKeywordLibrary(Client())]))
    suite = write_suite(tmp_path, {"name": "URL", "cases": [{"name": "case", "steps": [
        {"keyword": "HTTP GET", "args": [url]}]}]})
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--output-dir", str(root), "--html-report", "--allure"]) == 1
    assert received == [url]
    for file in latest(root).rglob("*"):
        if file.is_file():
            text = file.read_text(encoding="utf-8")
            assert encoded not in text, file
            assert "PRIVATE+URL TOKEN" not in text, file


def test_cli_allure_resolves_sensitive_variables_with_case_overrides(tmp_path):
    suite = write_suite(tmp_path, {"name": "Secrets", "variables": {"cred": "PRIVATE_SUITE_VALUE"},
        "keywords": {"Login": [{"keyword": "TYPE__TEXT", "args": ["id=password", "${cred}"]}]},
        "cases": [{"name": "suite value", "steps": [{"keyword": "Login"}]},
                  {"name": "case value", "variables": {"cred": "PRIVATE_CASE_VALUE"}, "steps": [{"keyword": "Login"}]}]})
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--dry-run", "--allure", "--output-dir", str(root)]) == 0
    for file in latest(root).rglob("*"):
        if file.is_file():
            content = file.read_text(encoding="utf-8")
            assert "PRIVATE_SUITE_VALUE" not in content
            assert "PRIVATE_CASE_VALUE" not in content


@pytest.mark.parametrize("stage", ["action", "preflight"])
def test_cli_interrupt_has_terminal_manifest_reports_and_resource_cleanup(tmp_path, monkeypatch, stage):
    calls, created, cleaned, handlers = [], [], [], []
    original_handler = cli.logging.FileHandler

    def capture_handler(*args, **kwargs):
        handler = original_handler(*args, **kwargs)
        handlers.append(handler)
        return handler

    def factory(*args):
        identifier = object()
        created.append(identifier)
        registry = KeywordRegistry(cleanup=lambda: cleaned.append(identifier))
        registry.register("Pass", lambda: calls.append("pass"))
        registry.register("Case Teardown", lambda: calls.append("case teardown"))
        registry.register("Suite Teardown", lambda: calls.append("suite teardown"))

        def interrupt():
            calls.append("interrupt")
            raise KeyboardInterrupt

        def validate(name, arguments):
            if stage == "preflight":
                raise KeyboardInterrupt

        registry.register("Interrupt", interrupt, validator=validate)
        return registry

    monkeypatch.setattr(cli, "_build_registry", factory)
    monkeypatch.setattr(cli.logging, "FileHandler", capture_handler)
    suite = write_suite(tmp_path, {"name": "Interrupt", "teardown": [{"keyword": "Suite Teardown"}],
        "cases": [{"name": "completed", "steps": [{"keyword": "Pass"}]},
                  {"name": "interrupted", "steps": [{"keyword": "Interrupt"}], "teardown": [{"keyword": "Case Teardown"}]},
                  {"name": "pending", "steps": [{"keyword": "Pass"}]}]})
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--output-dir", str(root), "--html-report", "--allure"]) == 130
    manifest = json.loads((root / "latest-run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "interrupted"
    directory = latest(root)
    result = json.loads((directory / "case-results.json").read_text(encoding="utf-8"))
    assert result["passed"] is False
    assert result["error_message"] == "Run interrupted"
    assert len(result["cases"]) == 3
    assert result["start"] <= result["stop"]
    if stage == "action":
        assert result["cases"][0]["passed"] is True
        assert result["cases"][1]["passed"] is False
        assert result["cases"][1]["blocked"] is False
        assert result["cases"][2]["blocked"] is True
        assert calls == ["pass", "interrupt", "case teardown", "suite teardown"]
    else:
        assert all(case["blocked"] for case in result["cases"])
        assert calls == []
    assert Counter(cleaned) == Counter(created)
    assert handlers and all(handler.stream is None for handler in handlers)
    assert (directory / "statistics.json").is_file()
    assert "Run interrupted" in (directory / "html-report" / "index.html").read_text(encoding="utf-8")
    exported = [json.loads(path.read_text(encoding="utf-8")) for path in (directory / "allure-results").glob("*-result.json")]
    assert any(item["status"] == "broken" and item["statusDetails"]["message"] == "Run interrupted" for item in exported)


def test_interrupted_case_retains_completed_steps_current_attempt_and_teardown(tmp_path, monkeypatch):
    cleaned = []

    def factory(*args):
        registry = KeywordRegistry(cleanup=lambda: cleaned.append(True))
        registry.register("Pass", lambda: None)
        registry.register("Case Teardown", lambda: None)

        def interrupt():
            raise KeyboardInterrupt

        registry.register("Interrupt", interrupt)
        return registry

    monkeypatch.setattr(cli, "_build_registry", factory)
    suite = write_suite(tmp_path, {"name": "Partial case", "cases": [{"name": "case", "retry": 2,
        "steps": [{"keyword": "Pass"}, {"keyword": "Interrupt"}], "teardown": [{"keyword": "Case Teardown"}]}]})
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--output-dir", str(root), "--allure"]) == 130
    result = json.loads((latest(root) / "case-results.json").read_text(encoding="utf-8"))
    case = result["cases"][0]
    assert not case["passed"] and not case["blocked"]
    assert len(case["attempts"]) == 1
    assert not case["attempts"][0]["passed"]
    assert case["steps"][0]["keyword"] == "Pass" and case["steps"][0]["passed"]
    assert any(step["keyword"] == "Case Teardown" and step["passed"] for step in case["steps"])
    assert any(not step["passed"] and step["error_message"] == "Run interrupted" for step in case["steps"])
    assert case["attempts"][0]["steps"] == case["steps"]
    assert len(cleaned) == 3


@pytest.mark.parametrize("interrupt_first", [False, True])
def test_parallel_interrupt_preserves_completed_cases_and_waits_for_running_case_cleanup(tmp_path, monkeypatch, interrupt_first):
    barrier = Barrier(2)
    completed_cleanup, interrupted_cleanup = Event(), Event()
    created, cleaned = [], []

    def factory(*args):
        identifier = object()
        created.append(identifier)
        active = None

        def cleanup():
            cleaned.append(identifier)
            if active == "completed":
                completed_cleanup.set()
            elif active == "interrupted":
                interrupted_cleanup.set()

        registry = KeywordRegistry(cleanup=cleanup)

        def start(name):
            nonlocal active
            active = name
            barrier.wait(timeout=5)
            if name == "interrupted":
                if not interrupt_first:
                    assert completed_cleanup.wait(timeout=5)
                raise KeyboardInterrupt
            if interrupt_first:
                assert interrupted_cleanup.wait(timeout=5)

        registry.register("Start", start)
        return registry

    monkeypatch.setattr(cli, "_build_registry", factory)
    names = ["interrupted", "completed"] if interrupt_first else ["completed", "interrupted"]
    suite = write_suite(tmp_path, {"name": "Parallel interrupt", "cases": [
        {"name": name, "steps": [{"keyword": "Start", "args": [name]}]} for name in names]})
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--workers", "2", "--output-dir", str(root), "--allure"]) == 130
    result = json.loads((latest(root) / "case-results.json").read_text(encoding="utf-8"))
    assert [case["name"] for case in result["cases"]] == names
    assert len(result["cases"]) == 2
    cases = {case["name"]: case for case in result["cases"]}
    assert cases["completed"]["passed"] and not cases["completed"]["blocked"]
    assert cases["completed"]["steps"][0]["keyword"] == "Start"
    assert not cases["interrupted"]["passed"] and not cases["interrupted"]["blocked"]
    assert cases["interrupted"]["attempts"] and not cases["interrupted"]["attempts"][0]["passed"]
    assert completed_cleanup.is_set() and interrupted_cleanup.is_set()
    assert Counter(cleaned) == Counter(created)
    assert json.loads((root / "latest-run.json").read_text(encoding="utf-8"))["status"] == "interrupted"


def test_parallel_cases_isolate_same_named_screenshots_and_export_real_images(tmp_path, monkeypatch):
    paths = []
    barrier = Barrier(2)

    def factory(*args):
        registry = KeywordRegistry()

        def screenshot(path):
            barrier.wait(timeout=5)
            output = Path(path)
            output.parent.mkdir(parents=True, exist_ok=True)
            image = png_bytes(1 + len(paths))
            output.write_bytes(image)
            paths.append(output)

        registry.register("Screenshot", screenshot)
        return registry

    monkeypatch.setattr(cli, "_build_registry", factory)
    suite = write_suite(tmp_path, {"name": "Parallel images", "cases": [
        {"name": name, "steps": [{"keyword": "Screenshot", "args": ["images/shared.png"]}]} for name in ["one", "two"]]})
    root = tmp_path / "out"
    before = time.time_ns() // 1_000_000
    assert cli.main(["run", str(suite), "--workers", "2", "--output-dir", str(root), "--html-report", "--allure"]) == 0
    after = time.time_ns() // 1_000_000
    directory = latest(root)
    result = json.loads((directory / "case-results.json").read_text(encoding="utf-8"))
    assert before <= result["start"] <= result["stop"] <= after
    assert len(paths) == len(set(paths)) == 2
    assert all(path.is_relative_to(directory) and path.name == "shared.png" for path in paths)
    recorded = [Path(case["steps"][0]["attachments"][0]["source"]) for case in result["cases"]]
    assert set(recorded) == set(paths)
    assert_screenshot_reports(directory, result, paths)


def test_case_retries_keep_separate_screenshot_files_and_report_history(tmp_path, monkeypatch):
    paths, attempts = [], []

    def factory(*args):
        registry = KeywordRegistry()

        def screenshot(path):
            output = Path(path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(png_bytes(len(paths) + 1))
            paths.append(output)

        def fail_once():
            attempts.append(True)
            if len(attempts) == 1:
                raise AssertionError("retry this case")

        registry.register("Screenshot", screenshot)
        registry.register("Fail Once", fail_once)
        return registry

    monkeypatch.setattr(cli, "_build_registry", factory)
    suite = write_suite(tmp_path, {"name": "Retry images", "cases": [{"name": "retry", "retry": 1,
        "steps": [{"keyword": "Screenshot", "args": ["shared.png"]}, {"keyword": "Fail Once"}]}]})
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--output-dir", str(root), "--html-report", "--allure"]) == 0
    directory = latest(root)
    result = json.loads((directory / "case-results.json").read_text(encoding="utf-8"))
    case = result["cases"][0]
    assert [attempt["passed"] for attempt in case["attempts"]] == [False, True]
    assert [path.parent.name for path in paths] == ["attempt-1", "attempt-2"]
    assert len(set(paths)) == 2
    assert paths[0].read_bytes() != paths[1].read_bytes()
    assert_screenshot_reports(directory, result, paths)


def test_screenshot_parent_escape_is_rejected_before_action(tmp_path, monkeypatch):
    called = []

    def factory(*args):
        registry = KeywordRegistry()
        registry.register("Screenshot", lambda path: called.append(path))
        return registry

    monkeypatch.setattr(cli, "_build_registry", factory)
    suite = write_suite(tmp_path, {"name": "Escape", "cases": [{"name": "case", "steps": [
        {"keyword": "Screenshot", "args": ["../escaped.png"]}]}]})
    root = tmp_path / "out"
    assert cli.main(["run", str(suite), "--output-dir", str(root)]) == 1
    assert called == []
    result = json.loads((latest(root) / "case-results.json").read_text(encoding="utf-8"))
    step = result["cases"][0]["steps"][0]
    assert step["failure_type"] == "validation"
    assert "inside the run directory" in step["error_message"]
    assert not list(tmp_path.rglob("escaped.png"))
