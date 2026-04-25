import json
from pathlib import Path

import pytest

import webtest_core.cli as cli
from webtest_core.cli import main


def test_cli_run_dry_run_generates_artifacts_and_html_report(tmp_path: Path):
    suite_file = tmp_path / "smoke.yaml"
    config_file = tmp_path / "runtime.yaml"
    output_dir = tmp_path / "artifacts"
    suite_file.write_text(
        """
suite:
  name: CliSmoke
  cases:
    - name: Dry run case
      module: auth
      tags: [smoke]
      steps:
        - keyword: Open
          args: ["https://example.test"]
        - keyword: Assert URL Contains
          args: [example]
""",
        encoding="utf-8",
    )
    config_file.write_text("browser: chrome\nheadless: true\n", encoding="utf-8")

    exit_code = main(
        [
            "run",
            str(suite_file),
            "--config",
            str(config_file),
            "--dry-run",
            "--html-report",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert json.loads((output_dir / "case-results.json").read_text(encoding="utf-8"))["suite"] == "CliSmoke"
    assert (output_dir / "statistics.json").exists()
    assert "CliSmoke" in (output_dir / "html-report" / "index.html").read_text(encoding="utf-8")


def test_cli_deploy_failure_short_circuits_execution_and_notifies(tmp_path: Path):
    suite_file = tmp_path / "smoke.yaml"
    config_file = tmp_path / "runtime.yaml"
    output_dir = tmp_path / "artifacts"
    suite_file.write_text(
        """
suite:
  name: DeploySuite
  cases:
    - name: Not executed
      steps:
        - keyword: Open
          args: ["https://example.test"]
""",
        encoding="utf-8",
    )
    config_file.write_text(
        """
pipeline:
  deploy:
    commands:
      - python -c "import sys; sys.exit(7)"
notifications:
  channels:
    - type: webhook
      enabled: false
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            str(suite_file),
            "--config",
            str(config_file),
            "--deploy",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads((output_dir / "case-results.json").read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["cases"][0]["name"] == "Not executed"
    assert payload["cases"][0]["failure_type"] == "deploy"


def test_cli_supports_run_empty_suite_rerun_failed_and_allure_environment(tmp_path: Path):
    suite_file = tmp_path / "smoke.yaml"
    rerun_file = tmp_path / "previous.json"
    output_dir = tmp_path / "artifacts"
    suite_file.write_text(
        """
suite:
  name: EmptySuite
  cases:
    - name: Selected By Rerun
      tags: [smoke]
      steps:
        - keyword: Open
          args: ["https://example.test"]
""",
        encoding="utf-8",
    )
    rerun_file.write_text(
        json.dumps({"suite": "old", "cases": [{"name": "Other", "passed": False}]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            str(suite_file),
            "--dry-run",
            "--run-empty-suite",
            "--rerun-failed",
            str(rerun_file),
            "--allure",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads((output_dir / "case-results.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["cases"] == []
    assert (output_dir / "allure-results" / "environment.properties").exists()


def test_cli_rejects_removed_rerunfailed_alias(tmp_path: Path):
    suite_file = tmp_path / "smoke.yaml"
    rerun_file = tmp_path / "previous.json"
    suite_file.write_text("suite:\n  name: AliasRemoved\n  cases: []\n", encoding="utf-8")
    rerun_file.write_text(json.dumps({"suite": "old", "cases": []}), encoding="utf-8")

    with pytest.raises(SystemExit):
        main(["run", str(suite_file), "--rerunfailed", str(rerun_file)])


def test_cli_builds_dingtalk_and_feishu_notification_senders(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "runtime.yaml"
    config_file.write_text(
        """
notifications:
  channels:
    - type: dingtalk
      enabled: true
      webhook: https://dingtalk.example/webhook
    - type: feishu
      enabled: true
      webhook: https://feishu.example/webhook
""",
        encoding="utf-8",
    )
    config = cli.load_runtime_config(config_file)

    channels = cli._notification_channels(config)

    assert channels[0].sender.__class__.__name__ == "DingtalkSender"
    assert channels[1].sender.__class__.__name__ == "FeishuSender"
