from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
import re
import time
from typing import Callable
from uuid import uuid4

from framework.dsl.models import CaseSpec, StepSpec, SuiteSpec
from framework.executor.execution_control import select_cases
from framework.executor.listener import ExecutionListener
from framework.executor.models import (
    CaseExecutionResult,
    FailureType,
    StepExecutionResult,
    SuiteExecutionResult,
