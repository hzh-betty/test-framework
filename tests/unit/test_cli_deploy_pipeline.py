import tempfile
import unittest
from pathlib import Path

from framework.cli.main import RuntimeDependencies, main


class FakeLogger:
    def __init__(self):
        self.info_messages = []
        self.error_messages = []

    def info(self, message: str):
        self.info_messages.append(message)

    def error(self, message: str):
        self.error_messages.append(message)


class FakeReporter:
    def write_suite_result(self, _result, context=None):
        return Path("artifacts/allure-results/executor-summary.json")

    def write_environment_properties(self, _context):
        return Path("artifacts/allure-results/environment.properties")

    def generate_html_report(self, output_dir):
        return True


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, **kwargs):
        self.sent.append(kwargs)


class FakeDriverManager:
    def create_driver(self, _config):
        return object()

    def quit_driver(self, _driver):
        return None


class TestCliDeployPipeline(unittest.TestCase):
    def test_deploy_failure_writes_failed_results_statistics_and_sends_notifications(self):
        logger = FakeLogger()
        notifier = FakeNotifier()
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: FakeDriverManager(),
            actions_factory=lambda _driver: object(),
            executor_factory=lambda _actions, _logger: (_ for _ in ()).throw(
                AssertionError("executor must not run after deploy failure")
            ),
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: notifier,
            dingtalk_notifier_factory=lambda _webhook: notifier,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            suite = root / "suite.yaml"
            config = root / "runtime.yaml"
            stats = root / "statistics.json"
            suite.write_text(
                """
name: Smoke
cases:
  - name: Login
    module: auth
    owner: alice
    steps: []
""",
                encoding="utf-8",
            )
            config.write_text(
                """
pipeline:
  deploy:
    commands:
      - python3 -c "import sys; sys.exit(3)"
notifications:
  channels:
    email:
      enabled: true
      trigger: on_failure
smtp:
  host: smtp.example.com
  port: 465
  username: bot@example.com
  password: secret
  sender: bot@example.com
  receivers: [qa@example.com]
""",
                encoding="utf-8",
            )

            rc = main(
                [
                    str(suite),
                    "--config",
                    str(config),
                    "--deploy",
                    "--notify",
                    "--stats-output",
                    str(stats),
                ],
                dependencies=deps,
            )

            self.assertEqual(rc, 1)
            self.assertTrue(stats.exists())
            self.assertIn("deploy command failed", stats.read_text(encoding="utf-8"))
            self.assertEqual(len(notifier.sent), 1)
            self.assertIn("Login", notifier.sent[0]["text"])


if __name__ == "__main__":
    unittest.main()
