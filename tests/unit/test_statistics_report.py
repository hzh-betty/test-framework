import json
import tempfile
import unittest
from pathlib import Path

from framework.executor.models import CaseExecutionResult, SuiteExecutionResult
from framework.reporting.statistics import build_statistics, write_statistics


class TestStatisticsReport(unittest.TestCase):
    def test_build_statistics_groups_by_metadata_and_tags(self):
        result = SuiteExecutionResult(
            name="StatsSuite",
            total_cases=3,
            passed_cases=1,
            failed_cases=2,
            case_results=[
                CaseExecutionResult(
                    name="Login",
                    passed=True,
                    module="auth",
                    type="ui",
                    priority="p0",
                    owner="alice",
                    tags=["smoke", "login"],
                ),
                CaseExecutionResult(
                    name="Checkout",
                    passed=False,
                    module="order",
                    type="ui",
                    priority="p1",
                    owner="bob",
                    tags=["smoke"],
                    failure_type="assertion",
                    error_message="text mismatch",
                ),
                CaseExecutionResult(
                    name="Profile",
                    passed=False,
                    tags=[],
                    failure_type="timeout",
                    error_message="slow",
                ),
            ],
        )

        stats = build_statistics(result)

        self.assertEqual(stats["overall"]["total"], 3)
        self.assertEqual(stats["overall"]["passed"], 1)
        self.assertEqual(stats["overall"]["failed"], 2)
        self.assertEqual(stats["overall"]["pass_rate"], 33.33)
        self.assertEqual(stats["module"]["auth"]["pass_rate"], 100.0)
        self.assertEqual(stats["module"]["unassigned"]["failed_cases"][0]["name"], "Profile")
        self.assertEqual(stats["owner"]["bob"]["failed_cases"][0]["failure_type"], "assertion")
        self.assertEqual(stats["tag"]["smoke"]["total"], 2)
        self.assertEqual(stats["tag"]["unassigned"]["failed"], 1)

    def test_write_statistics_persists_json_artifact(self):
        result = SuiteExecutionResult(
            name="StatsSuite",
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            case_results=[CaseExecutionResult(name="Login", passed=True, module="auth")],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = write_statistics(Path(tmpdir) / "statistics.json", result)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["suite"], "StatsSuite")
        self.assertEqual(payload["module"]["auth"]["passed"], 1)


if __name__ == "__main__":
    unittest.main()
