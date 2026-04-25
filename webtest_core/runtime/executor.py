"""测试套件执行器。

执行器接收已经校验过的 ``SuiteSpec``，并通过 ``KeywordRegistry`` 调用关键字。
重试、失败继续、dry-run、并行和 suite/case 生命周期都集中在这里，避免报告
或 CLI 重复理解执行语义。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from webtest_core.dsl import CaseSpec, Scalar, StepSpec, SuiteSpec, interpolate
from webtest_core.keywords import KeywordRegistry
from webtest_core.runtime.filtering import select_cases
from webtest_core.runtime.models import CaseResult, FailureType, StepResult, SuiteResult


class SuiteExecutor:
    """使用关键字注册表执行一个测试套件。"""

    def __init__(self, registry: KeywordRegistry, *, dry_run: bool = False):
        self.registry = registry
        self.dry_run = dry_run

    def run_suite(
        self,
        suite: SuiteSpec,
        *,
        include_tag_expr: str | None = None,
        exclude_tag_expr: str | None = None,
        modules: set[str] | None = None,
        case_types: set[str] | None = None,
        priorities: set[str] | None = None,
        owners: set[str] | None = None,
        allowed_case_names: set[str] | None = None,
        workers: int = 1,
        run_empty_suite: bool = True,
    ) -> SuiteResult:
        selected_cases = select_cases(
            suite.cases,
            include_tag_expr=include_tag_expr,
            exclude_tag_expr=exclude_tag_expr,
            modules=modules,
            case_types=case_types,
            priorities=priorities,
            owners=owners,
            allowed_case_names=allowed_case_names,
        )
        if not selected_cases and not run_empty_suite:
            raise ValueError("Suite contains no runnable cases after filtering.")

        suite_variables = dict(suite.variables)
        setup_steps: list[StepResult] = []
        setup_ok = self._run_steps(
            suite.setup,
            suite_variables,
            suite.keywords,
            setup_steps,
            case_attempt=1,
            case_max_retries=0,
        )

        if not setup_ok:
            case_results = [
                CaseResult(
                    name=case.name,
                    passed=False,
                    error_message="Suite setup failed.",
                    failure_type="action",
                    module=case.module,
                    type=case.type,
                    priority=case.priority,
                    owner=case.owner,
                    tags=list(case.tags),
                )
                for case in selected_cases
            ]
        elif workers > 1 and len(selected_cases) > 1:
            case_results = self._run_parallel(suite, selected_cases, workers)
        else:
            case_results = [self._run_case(suite, case) for case in selected_cases]

        teardown_steps: list[StepResult] = []
        teardown_ok = self._run_steps(
            suite.teardown,
            suite_variables,
            suite.keywords,
            teardown_steps,
            case_attempt=1,
            case_max_retries=0,
        )
        if not teardown_ok:
            case_results.append(
                CaseResult(
                    name=f"{suite.name}::suite_teardown",
                    passed=False,
                    step_results=teardown_steps,
                    error_message=_first_error(teardown_steps),
                    failure_type=_first_failure_type(teardown_steps),
                )
            )

        passed = sum(1 for case in case_results if case.passed)
        failed = len(case_results) - passed
        return SuiteResult(
            name=suite.name,
            total_cases=len(case_results),
            passed_cases=passed,
            failed_cases=failed,
            case_results=case_results,
            suite_teardown_failed=not teardown_ok,
            suite_teardown_error_message=_first_error(teardown_steps) if not teardown_ok else None,
            suite_teardown_failure_type=_first_failure_type(teardown_steps) if not teardown_ok else None,
        )

    def _run_parallel(self, suite: SuiteSpec, cases: list[CaseSpec], workers: int) -> list[CaseResult]:
        ordered: list[CaseResult | None] = [None] * len(cases)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._run_case, suite, case): index
                for index, case in enumerate(cases)
            }
            for future in as_completed(futures):
                ordered[futures[future]] = future.result()
        return [case for case in ordered if case is not None]

    def _run_case(self, suite: SuiteSpec, case: CaseSpec) -> CaseResult:
        case_trace: list[dict[str, object]] = []
        final_result: CaseResult | None = None
        for attempt in range(1, case.retry + 2):
            final_result = self._run_case_once(suite, case, attempt)
            for step in final_result.step_results:
                step.case_attempt = attempt
                step.case_max_retries = case.retry
            if final_result.passed:
                if case_trace and final_result.step_results:
                    final_result.step_results[0].retry_trace = [*case_trace]
                return final_result
            case_trace.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "error": final_result.error_message or "case failed",
                }
            )
            if attempt > case.retry:
                break
        if final_result and case_trace:
            for step in final_result.step_results:
                step.retry_trace = [*case_trace]
        return final_result or CaseResult(name=case.name, passed=False)

    def _run_case_once(self, suite: SuiteSpec, case: CaseSpec, case_attempt: int) -> CaseResult:
        variables = {**suite.variables, **case.variables}
        step_results: list[StepResult] = []
        passed = self._run_steps(
            case.setup,
            variables,
            suite.keywords,
            step_results,
            case_attempt=case_attempt,
            case_max_retries=case.retry,
        )
        if passed:
            passed = self._run_steps(
                case.steps,
                variables,
                suite.keywords,
                step_results,
                continue_on_failure=case.continue_on_failure,
                case_attempt=case_attempt,
                case_max_retries=case.retry,
            )
        teardown_passed = self._run_steps(
            case.teardown,
            variables,
            suite.keywords,
            step_results,
            case_attempt=case_attempt,
            case_max_retries=case.retry,
        )
        passed = passed and teardown_passed
        return CaseResult(
            name=case.name,
            passed=passed,
            step_results=step_results,
            error_message=None if passed else _first_error(step_results),
            failure_type=None if passed else _first_failure_type(step_results),
            module=case.module,
            type=case.type,
            priority=case.priority,
            owner=case.owner,
            tags=list(case.tags),
        )

    def _run_steps(
        self,
        steps: list[StepSpec],
        variables: dict[str, Scalar],
        user_keywords: dict[str, list[StepSpec]],
        step_results: list[StepResult],
        *,
        continue_on_failure: bool = False,
        call_chain: list[str] | None = None,
        case_attempt: int = 1,
        case_max_retries: int = 0,
    ) -> bool:
        passed = True
        for step in steps:
            current_chain = [*(call_chain or []), step.keyword]
            if step.keyword in user_keywords:
                nested_ok = self._run_steps(
                    user_keywords[step.keyword],
                    variables,
                    user_keywords,
                    step_results,
                    continue_on_failure=continue_on_failure or step.continue_on_failure,
                    call_chain=current_chain,
                    case_attempt=case_attempt,
                    case_max_retries=case_max_retries,
                )
                passed = passed and nested_ok
                if not nested_ok and not (continue_on_failure or step.continue_on_failure):
                    return False
                continue

            result = self._run_step(
                step,
                variables,
                call_chain=current_chain,
                case_attempt=case_attempt,
                case_max_retries=case_max_retries,
            )
            step_results.append(result)
            if not result.passed:
                passed = False
                if not (continue_on_failure or step.continue_on_failure):
                    return False
        return passed

    def _run_step(
        self,
        step: StepSpec,
        variables: dict[str, Scalar],
        *,
        call_chain: list[str],
        case_attempt: int,
        case_max_retries: int,
    ) -> StepResult:
        args = interpolate(step.args, variables)
        kwargs = interpolate(step.kwargs, variables)
        if step.timeout is not None and "timeout" not in kwargs:
            kwargs = {**kwargs, "timeout": interpolate(step.timeout, variables)}
        max_retries = step.retry
        retry_trace: list[dict[str, object]] = []
        for attempt in range(1, max_retries + 2):
            started = time.perf_counter()
            try:
                if not self.registry.has(step.keyword):
                    raise KeyError(f"Unknown keyword: {step.keyword}")
                if not self.dry_run:
                    self.registry.run(step.keyword, list(args), dict(kwargs))
                duration_ms = int((time.perf_counter() - started) * 1000)
                return StepResult(
                    keyword=step.keyword,
                    passed=True,
                    arguments=list(args),
                    kwargs=dict(kwargs),
                    dry_run=self.dry_run,
                    call_chain=list(call_chain),
                    duration_ms=duration_ms,
                    retry_attempt=attempt,
                    retry_max_retries=max_retries,
                    case_attempt=case_attempt,
                    case_max_retries=case_max_retries,
                    retry_trace=[*retry_trace],
                    resolved_locator=_resolved_locator(args),
                    current_url=_current_url(self.registry),
                )
            # 关键字库可能抛出任意异常；执行器必须把它们转换成结构化结果，
            # 否则报告、通知和重跑失败都无法获得稳定的数据。
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                failure_type = _classify_failure(exc)
                if attempt <= max_retries:
                    retry_trace.append(
                        {
                            "attempt": attempt,
                            "status": "failed",
                            "error": str(exc),
                        }
                    )
                    continue
                return StepResult(
                    keyword=step.keyword,
                    passed=False,
                    arguments=list(args),
                    kwargs=dict(kwargs),
                    dry_run=self.dry_run,
                    error_message=str(exc),
                    failure_type=failure_type,
                    call_chain=list(call_chain),
                    duration_ms=duration_ms,
                    retry_attempt=attempt,
                    retry_max_retries=max_retries,
                    case_attempt=case_attempt,
                    case_max_retries=case_max_retries,
                    retry_trace=[*retry_trace],
                    resolved_locator=_resolved_locator(args),
                    current_url=_current_url(self.registry),
                )


def _classify_failure(exc: Exception) -> FailureType:
    if isinstance(exc, KeyError):
        return "validation"
    if isinstance(exc, AssertionError):
        return "assertion"
    return "action"


def _first_error(steps: list[StepResult]) -> str | None:
    for step in steps:
        if not step.passed:
            return step.error_message
    return None


def _first_failure_type(steps: list[StepResult]) -> FailureType | None:
    for step in steps:
        if not step.passed:
            return step.failure_type
    return None


def _resolved_locator(args: object) -> dict[str, str] | None:
    if not isinstance(args, list) or not args or not isinstance(args[0], str):
        return None
    raw = args[0]
    if raw.startswith(("http://", "https://", "/")):
        return None
    if "=" in raw:
        by, value = raw.split("=", 1)
    else:
        by, value = "css", raw
    return {"raw": raw, "by": by, "value": value}


def _current_url(registry: KeywordRegistry) -> str | None:
    for definition in getattr(registry, "_keywords", {}).values():
        actions = getattr(getattr(definition.func, "__self__", None), "actions", None)
        driver = getattr(actions, "driver", None)
        current_url = getattr(driver, "current_url", None)
        if isinstance(current_url, str):
            return current_url
    return None
