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

