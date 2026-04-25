from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import inspect
import platform
from pathlib import Path
import subprocess
import threading
from typing import Callable, Sequence

from framework import __version__
from framework.core import load_runtime_config
from framework.dsl.models import SuiteSpec
from framework.executor import CaseExecutionResult, Executor, SuiteExecutionResult
from framework.executor.execution_control import select_cases
from framework.keywords import load_keyword_libraries, load_listeners
from framework.logging import configure_runtime_logger
from framework.notify import (
    DingTalkNotifier,
    EmailNotifier,
    NotificationDispatcher,
    SmtpConfig,
    WebhookNotifier,
)
from framework.page_objects.base_page import BasePage
from framework.parser import get_parser
from framework.reporting import AllureReporter, ReportContext, build_statistics, write_statistics
from framework.reporting.case_results import read_failed_case_names, write_case_results
from framework.reporting.result_merge import (
    load_merged_suite_result,
    parse_merge_results_argument,
)
from framework.selenium import (
    BrowserSessionManager,
    DriverConfig,
    DriverManager,
    SeleniumActions,
    SessionActionsProxy,
)
