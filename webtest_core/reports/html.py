"""内置静态 HTML 报告。

HTML 报告用于本地快速查看结果，不依赖 Allure CLI。这里直接渲染字符串，
是因为当前页面结构简单；等报告复杂后再引入模板引擎更合适。
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from webtest_core.runtime import CaseResult, SuiteResult


def write_html_report(output_dir: str | Path, result: SuiteResult, statistics: dict) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "index.html"
    path.write_text(_render_html(result, statistics), encoding="utf-8")
    return path


def _render_html(result: SuiteResult, statistics: dict) -> str:
    case_rows = "\n".join(_render_case(case) for case in result.case_results)
    overall = statistics["overall"]
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
      <div class="metric"><span>通过率</span><strong>{overall["pass_rate"]}%</strong></div>
    </div>
    <section><h2>用例</h2>{case_rows or '<p>没有执行任何用例。</p>'}</section>
  </main>
</body>
</html>
"""


def _render_case(case: CaseResult) -> str:
    status_class = "passed" if case.passed else "failed"
    status_label = "通过" if case.passed else "失败"
    steps = "".join(
        f"<tr><td>{escape(step.keyword)}</td><td class=\"{'passed' if step.passed else 'failed'}\">{'通过' if step.passed else '失败'}</td><td>{escape(step.error_message or '')}</td></tr>"
        for step in case.step_results
    )
    return (
        f"<article><h3>{escape(case.name)} <span class=\"{status_class}\">{status_label}</span></h3>"
        f"<p class=\"meta\">模块={escape(case.module or '未分配')} 负责人={escape(case.owner or '未分配')}</p>"
        f"<p class=\"failed\">{escape(case.error_message or '')}</p>"
        f"<table><tr><th>步骤</th><th>状态</th><th>错误信息</th></tr>{steps}</table></article>"
    )
