import tempfile
import unittest
from pathlib import Path

from framework.logging.runtime_logger import FailureContext, configure_runtime_logger


class TestLoggingModule(unittest.TestCase):
    def test_configure_runtime_logger_writes_log_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            logger = configure_runtime_logger("framework.runtime", log_file=str(log_file))
            logger.info("suite started")

            content = log_file.read_text(encoding="utf-8")
            self.assertIn("suite started", content)

    def test_failure_context_is_logged_as_structured_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            logger = configure_runtime_logger("framework.runtime.failure", log_file=str(log_file))
            context = FailureContext(
                url="https://example.test/dashboard",
                locator="id=submit",
                screenshot_path="artifacts/failure.png",
                error="NoSuchElementException",
            )

            logger.error(context.to_log_message())

            content = log_file.read_text(encoding="utf-8")
            self.assertIn("url=https://example.test/dashboard", content)
            self.assertIn("locator=id=submit", content)
            self.assertIn("screenshot=artifacts/failure.png", content)


if __name__ == "__main__":
    unittest.main()
