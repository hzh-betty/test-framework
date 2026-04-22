import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from framework.cli.main import RuntimeDependencies, build_parser, main
from framework.core import load_runtime_config
from framework.executor.models import CaseExecutionResult, SuiteExecutionResult


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


class FakeExecutor:
    def __init__(self, result: SuiteExecutionResult):
        self.result = result
        self.run_file_calls = []

    def run_file(self, dsl_path: str, **kwargs):
        self.run_file_calls.append((dsl_path, kwargs))
        return self.result


class TestCliPipeline(unittest.TestCase):
    def test_parser_exposes_metadata_stats_deploy_and_notify_options(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "suite.yaml",
                "--module",
                "auth,order",
                "--module",
                "profile",
                "--case-type",
                "ui",
                "--priority",
                "p0",
                "--owner",
                "alice",
                "--stats-output",
                "out/stats.json",
                "--deploy",
                "--notify",
            ]
        )

        self.assertEqual(args.module, ["auth,order", "profile"])
        self.assertEqual(args.case_type, ["ui"])
        self.assertEqual(args.priority, ["p0"])
        self.assertEqual(args.owner, ["alice"])
        self.assertEqual(args.stats_output, "out/stats.json")
        self.assertTrue(args.deploy)
        self.assertTrue(args.notify)

    def test_main_passes_metadata_filters_and_writes_statistics(self):
        logger = FakeLogger()
        executor = FakeExecutor(
            SuiteExecutionResult(
                name="Smoke",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                case_results=[
                    CaseExecutionResult(
                        name="Login",
                        passed=True,
                        module="auth",
                        type="ui",
                        priority="p0",
                        owner="alice",
                    )
                ],
            )
        )
        deps = RuntimeDependencies(
            driver_manager_factory=lambda: FakeDriverManager(),
            actions_factory=lambda _driver: object(),
            executor_factory=lambda _actions, _logger: executor,
            reporter_factory=lambda _results_dir: FakeReporter(),
            logger_factory=lambda _level, _file: logger,
            email_notifier_factory=lambda _config: FakeNotifier(),
            dingtalk_notifier_factory=lambda _webhook: FakeNotifier(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            suite = root / "suite.yaml"
            stats = root / "statistics.json"
            suite.write_text(
                """
name: Smoke
cases:
  - name: Login
    module: auth
    type: ui
    priority: p0
    owner: alice
    steps: []
""",
                encoding="utf-8",
            )

            rc = main(
                [
                    str(suite),
                    "--module",
                    "auth,order",
                    "--case-type",
                    "ui",
                    "--priority",
                    "p0",
                    "--owner",
                    "alice",
                    "--stats-output",
                    str(stats),
                ],
                dependencies=deps,
            )

            self.assertEqual(rc, 0)
            kwargs = executor.run_file_calls[0][1]
            self.assertEqual(kwargs["modules"], {"auth", "order"})
            self.assertEqual(kwargs["case_types"], {"ui"})
            self.assertEqual(kwargs["priorities"], {"p0"})
            self.assertEqual(kwargs["owners"], {"alice"})
            self.assertTrue(stats.exists())

    def test_runtime_config_expands_environment_variables_recursively(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "runtime.yaml"
            config.write_text(
                """
smtp:
  password: ${SMTP_PASSWORD}
notifications:
  channels:
    dingtalk:
      webhook: ${DINGTALK_WEBHOOK}
""",
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {
                    "SMTP_PASSWORD": "secret",
                    "DINGTALK_WEBHOOK": "https://example.test/webhook",
                },
            ):
                loaded = load_runtime_config(str(config))

        self.assertEqual(loaded["smtp"]["password"], "secret")
        self.assertEqual(
            loaded["notifications"]["channels"]["dingtalk"]["webhook"],
            "https://example.test/webhook",
        )


if __name__ == "__main__":
    unittest.main()
