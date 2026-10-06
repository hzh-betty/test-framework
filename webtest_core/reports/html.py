"""内置静态 HTML 报告。

HTML 报告用于本地快速查看结果，不依赖 Allure CLI。这里直接渲染字符串，
是因为当前页面结构简单；等报告复杂后再引入模板引擎更合适。
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from webtest_core.redaction import Redactor
from webtest_core.reports.attachments import copy_screenshots
from webtest_core.reports.statistics import safe_statistics
from webtest_core.runtime import CaseResult, SuiteResult


def write_html_report(output_dir: str | Path, result: SuiteResult, statistics: dict, *,
                      redactor: Redactor | None = None) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "index.html"
    redactor = redactor or Redactor()
    statistics = safe_statistics(result, statistics, redactor=redactor)
    safe_result = redactor.redact_result(result)
    copy_screenshots(result, safe_result, output / "attachments")
    path.write_text(_render_html(safe_result, statistics), encoding="utf-8")
    return path


def _render_html(result: SuiteResult, statistics: dict) -> str:
    case_rows = "\n".join(_render_case(case) for case in result.case_results)
    overall = statistics["overall"]
    lifecycle_rows = "".join(_render_lifecycle(item) for item in result.suite_results or [result])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(result.name)} 测试报告</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f6f7f9; color: #1f2933; }}
    header, main {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
    header {{ background: #fff; border-bottom: 1px solid #d9dee7; max-width: none; }}
    section, .metric, article {{ background: #fff; border: 1px solid #d9dee7; border-radius: 8px; padding: 16px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .metric span {{ color: #667085; display: block; font-size: 13px; }}
    .metric strong {{ font-size: 26px; }}
    .passed {{ color: #13795b; }}
    .failed {{ color: #b42318; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #d9dee7; padding: 8px; text-align: left; }}
    article {{ margin: 12px 0; }}
    .meta {{ color: #667085; font-size: 13px; }}
  </style>
</head>
<body>
  <header><h1>{escape(result.name)}</h1><p>测试报告</p></header>
  <main>
    <div class="metrics">
      <div class="metric"><span>用例总数</span><strong>{overall["total"]}</strong></div>
      <div class="metric"><span>通过</span><strong class="passed">{overall["passed"]}</strong></div>
      <div class="metric"><span>失败</span><strong class="failed">{overall["failed"]}</strong></div>
      <div class="metric"><span>未执行</span><strong>{overall["blocked"]}</strong></div>
      <div class="metric"><span>通过率</span><strong>{overall["pass_rate"]}%</strong></div>
    </div>
    <section><h2>运行状态：{'通过' if result.passed else '失败'}</h2>{lifecycle_rows}</section>
    <section><h2>用例</h2>{case_rows or '<p>没有执行任何用例。</p>'}</section>
    <section><h2>通知</h2><p>{escape('; '.join(_notification_errors(result)))}</p></section>
  </main>
</body>
</html>
"""


def _render_case(case: CaseResult) -> str:
    status_class = "passed" if case.passed else "failed"
    status_label = "未执行" if case.blocked else ("通过" if case.passed else "失败")
    steps = _render_steps(case.step_results)
    history = "".join(f"<details><summary>尝试 {attempt.attempt}：{'通过' if attempt.passed else '失败'}</summary><table>{_render_steps(attempt.steps)}</table></details>" for attempt in case.attempts[:-1])
    return (
        f"<article><h3>{escape(case.name)} <span class=\"{status_class}\">{status_label}</span></h3>"
        f"<p class=\"meta\">模块={escape(case.module or '未分配')} 负责人={escape(case.owner or '未分配')}</p>"
        f"<p class=\"failed\">{escape(case.error_message or '')}</p>"
        f"<table><tr><th>步骤</th><th>状态</th><th>错误信息</th></tr>{steps}</table>{history}</article>"
    )


def _render_steps(steps):
    return "".join(
        f"<tr><td>{escape(' → '.join(step.call_chain) or step.keyword)}</td><td class=\"{'passed' if step.passed else 'failed'}\">{'通过' if step.passed else '失败'}</td><td>{escape(step.error_message or '')} {_render_attachments(step)}</td></tr>{_render_steps(step.children)}"
        for step in steps)


def _render_attachments(step):
    return " ".join(f'<a href="attachments/{escape(item["source"], quote=True)}">{escape(item["name"])}</a>'
                    for item in step.attachments)


def _render_lifecycle(result):
    return (f"<article><h3>{escape(result.name)}</h3><p class=\"failed\">{escape(result.error_message or '')}</p>"
            f"<h4>初始化</h4><table>{_render_steps(result.setup_steps)}</table>"
            f"<h4>清理</h4><table>{_render_steps(result.teardown_steps)}</table></article>")


def _notification_errors(result):
    errors = list(result.notification_errors)
    for suite in result.suite_results:
        errors.extend(f"{suite.name}: {error}" for error in _notification_errors(suite))
    return errors
