from pathlib import Path

import pytest

from webtest_core.dsl import DslValidationError, load_runtime_config, load_suite


def test_load_suite_accepts_yaml_v1_and_normalizes_defaults(tmp_path: Path):
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
suite:
  name: Smoke
  variables:
    base_url: https://example.test
  keywords:
    Login:
      - keyword: Open
        args: ["${base_url}/login"]
  setup:
    - keyword: Login
  cases:
    - name: Can open dashboard
      module: auth
      type: ui
      priority: p0
      owner: qa
      tags: [smoke, login]
      retry: 1
      continue_on_failure: false
      steps:
        - keyword: Assert URL Contains
          args: ["/login"]
          timeout: 2s
  teardown:
    - keyword: Close Browser
""",
        encoding="utf-8",
    )

    suite = load_suite(suite_file)

    assert suite.name == "Smoke"
    assert suite.variables == {"base_url": "https://example.test"}
    assert suite.setup[0].keyword == "Login"
    assert suite.keywords["Login"][0].args == ["${base_url}/login"]
    assert suite.cases[0].tags == ["smoke", "login"]
    assert suite.cases[0].steps[0].timeout == "2s"


def test_load_suite_rejects_non_yaml_and_reports_validation_errors(tmp_path: Path):
    json_file = tmp_path / "suite.json"
    json_file.write_text('{"suite": {"name": "Nope", "cases": []}}', encoding="utf-8")
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("suite:\n  cases: []\n", encoding="utf-8")

    with pytest.raises(DslValidationError, match="Only YAML DSL files are supported"):
        load_suite(json_file)
    with pytest.raises(DslValidationError, match="suite.name"):
        load_suite(bad_yaml)


def test_load_suite_rejects_legacy_action_target_value_fields(tmp_path: Path):
    suite_file = tmp_path / "legacy.yaml"
    suite_file.write_text(
        """
suite:
  name: LegacySuite
  cases:
    - name: Legacy case
      steps:
        - action: open
          target: https://example.test
          value: ignored
""",
        encoding="utf-8",
    )

    with pytest.raises(DslValidationError, match="Extra inputs are not permitted"):
        load_suite(suite_file)


def test_load_suite_accepts_nested_args_kwargs_for_http_payloads(tmp_path: Path):
    suite_file = tmp_path / "http.yaml"
    suite_file.write_text(
        """
suite:
  name: ApiSuite
  cases:
    - name: Create user
      steps:
        - keyword: HTTP POST
          args:
            - https://api.example.test/users
          kwargs:
            headers:
              Authorization: Bearer demo-token
            json:
              name: Alice
              roles: [admin, editor]
        - keyword: Assert Response JSON
          args: ["data.roles.0", admin]
""",
        encoding="utf-8",
    )

    suite = load_suite(suite_file)

    assert suite.cases[0].steps[0].kwargs == {
        "headers": {"Authorization": "Bearer demo-token"},
        "json": {"name": "Alice", "roles": ["admin", "editor"]},
    }


def test_runtime_config_expands_environment_variables(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    config_file = tmp_path / "runtime.yaml"
    config_file.write_text(
        """
browser: firefox
headless: true
timeouts:
  implicit_wait: 4
notifications:
  channels:
    - type: email
      enabled: true
      trigger: on_failure
      retries: 2
      smtp:
        host: smtp.example.com
        port: 465
        username: bot
        password: ${SMTP_PASSWORD}
        sender: bot@example.com
        receivers: [qa@example.com]
""",
        encoding="utf-8",
    )

    config = load_runtime_config(config_file)

    assert config.browser == "firefox"
    assert config.headless is True
    assert config.timeouts.implicit_wait == 4
    assert config.notifications.channels[0].smtp.password == "secret"
