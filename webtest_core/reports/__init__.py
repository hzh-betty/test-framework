"""报告模块公共 API。

具体实现拆分到多个文件；这里保留原有导入路径，避免影响调用方。
"""

from webtest_core.reports.allure import write_allure_results
from webtest_core.reports.case_results import (
    merge_case_results,
    read_failed_case_names,
    write_case_results,
)
from webtest_core.reports.html import write_html_report
from webtest_core.reports.statistics import build_statistics, write_statistics

__all__ = [
    "build_statistics",
    "merge_case_results",
    "read_failed_case_names",
    "write_allure_results",
    "write_case_results",
    "write_html_report",
    "write_statistics",
]
