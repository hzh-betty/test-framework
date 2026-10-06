"""套件生命周期与每次用例尝试使用独立注册表，预检查先于执行。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Callable
from uuid import uuid4

from webtest_core.browser.locators import parse_locator
from webtest_core.dsl import CaseSpec, DslValidationError, StepSpec, SuiteSpec, interpolate
from webtest_core.dsl.durations import seconds
from webtest_core.keywords import KeywordRegistry, normalize_keyword_name
from webtest_core.redaction import Redactor, sensitive_key
from webtest_core.runtime.filtering import select_cases
from webtest_core.runtime.models import CaseAttempt, CaseResult, StepResult, SuiteResult


@dataclass
class _Context:
    registry: KeywordRegistry
    redactor: Redactor
    output_dir: Path | None = None


class _CaseInterrupted(KeyboardInterrupt):
    def __init__(self, result: CaseResult):
        super().__init__("Run interrupted")
        self.result = result


class SuiteExecutor:
    def __init__(self, registry_factory: Callable[[], KeywordRegistry], *, dry_run: bool = False,
                 redactor: Redactor | None = None, output_dir: str | Path | None = None):
        self.registry_factory = registry_factory
        self.dry_run = dry_run
        self.redactor = redactor if redactor is not None else Redactor()
        self.output_dir = Path(output_dir) if output_dir is not None else None

    def _context(self, suite, secrets=None, output_dir=None) -> _Context:
        if secrets is None:
            self.redactor.collect_suite(suite.model_dump())
        redactor = Redactor()
        redactor.secrets.update(self.redactor.secrets if secrets is None else secrets)
        return _Context(self.registry_factory(), redactor, output_dir)

    def validate_suite(self, suite: SuiteSpec, cases: list[CaseSpec] | None = None):
        """无动作的预检查；工厂必须创建新的库对象，不能预先启动浏览器。"""
        try:
            context = self._context(suite)
        except Exception as exc:
            raise RuntimeError(self.redactor.redact(str(exc))) from None
        try:
            keywords = {}
            for name, steps in suite.keywords.items():
                normalized = normalize_keyword_name(name)
                if not normalized or normalized in keywords or context.registry.has(name):
                    raise DslValidationError(f"Duplicate or reserved composite keyword: {name}")
                keywords[normalized] = steps

            visited = set()
            visiting = set()
            path = []

            def check_cycle(name):
                if name in visiting:
                    raise DslValidationError("Composite keyword cycle: " + " -> ".join([*path, name]))
                if name in visited:
                    return
                visiting.add(name)
                path.append(name)
                for step in keywords[name]:
                    child = normalize_keyword_name(step.keyword)
                    if child in keywords:
                        check_cycle(child)
                    elif not context.registry.has(step.keyword):
                        raise DslValidationError(f"Unknown keyword: {step.keyword}")
                visited.add(name)
                path.pop()
                visiting.remove(name)

            for name in keywords:
                check_cycle(name)

            def check_steps(steps, variables, chain=()):
                for step in steps:
                    current = (*chain, step.keyword)
                    try:
                        args, kwargs, bound = self._prepare(step, variables, context, keywords)
                        normalized = normalize_keyword_name(step.keyword)
                        if normalized in keywords:
                            check_steps(keywords[normalized], variables, current)
                    except DslValidationError as exc:
                        raise DslValidationError(context.redactor.redact(" -> ".join(current) + ": " + str(exc))) from None

            check_steps(suite.setup + suite.teardown, suite.variables)
            for case in suite.cases if cases is None else cases:
                check_steps(case.setup + case.steps + case.teardown, {**suite.variables, **case.variables}, (case.name,))
            return keywords, frozenset(context.redactor.secrets)
        finally:
            self.redactor.secrets.update(context.redactor.secrets)
            if context.registry.cleanup:
                try:
                    context.registry.cleanup()
                except Exception as exc:
                    raise RuntimeError(context.redactor.redact(str(exc))) from None

    def run_suite(self, suite: SuiteSpec, *, include_tag_expr=None, exclude_tag_expr=None,
                  modules=None, case_types=None, priorities=None, owners=None,
                  allowed_case_names=None, workers: int = 1, run_empty_suite: bool = False) -> SuiteResult:
        result = SuiteResult(suite.name, start=_now_ms())
        selected = suite.cases
        context = None
        try:
            if workers < 1:
                raise DslValidationError("workers must be at least 1")
            selected = select_cases(suite.cases, include_tag_expr=include_tag_expr, exclude_tag_expr=exclude_tag_expr,
                                    modules=modules, case_types=case_types, priorities=priorities,
                                    owners=owners, allowed_case_names=allowed_case_names)
            if not selected and not run_empty_suite:
                raise DslValidationError("Suite contains no runnable cases after filtering.")
            keywords, secrets = self.validate_suite(suite, selected)
            context = self._context(suite, secrets, self.output_dir / "suite" if self.output_dir else None)
            setup_ok = self._run_steps(suite.setup, suite.variables, keywords, result.setup_steps, context)
            if not setup_ok:
                result.case_results = [self._case_result(suite, case, passed=False, blocked=True,
                    error_message=_first_error(result.setup_steps), failure_type=_first_failure_type(result.setup_steps)) for case in selected]
            elif workers > 1 and len(selected) > 1:
                interrupted = None
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(self._run_case, suite, case, keywords, secrets) for case in selected]
                    for future in futures:
                        try:
                            result.case_results.append(future.result())
                        except KeyboardInterrupt as exc:
                            interrupted = exc
                            for pending in futures:
                                pending.cancel()
                            break
                if interrupted is not None:
                    # 已运行的线程不能安全终止；pool 完成清理后保留结果，未开始的任务保持 blocked。
                    completed = {case.name for case in result.case_results}
                    for future in futures:
                        if future.cancelled():
                            continue
                        try:
                            case = future.result()
                        except _CaseInterrupted as exc:
                            case = exc.result
                        if case.name not in completed:
                            result.case_results.append(case)
                            completed.add(case.name)
                    raise interrupted
            else:
                for case in selected:
                    result.case_results.append(self._run_case(suite, case, keywords, secrets))
        except KeyboardInterrupt as exc:
            result.error_message = "Run interrupted"
            result.failure_type = "action"
            completed = {case.name: case for case in result.case_results}
            if isinstance(exc, _CaseInterrupted):
                completed.setdefault(exc.result.name, exc.result)
            result.case_results = [completed[case.name] if case.name in completed else
                self._case_result(suite, case, passed=False, blocked=True,
                    error_message="Run interrupted", failure_type="action") for case in selected]
            raise
        except Exception as exc:
            redactor = context.redactor if context else self.redactor
            result.error_message = redactor.redact(str(exc))
            result.failure_type = _classify_failure(exc)
            if not result.case_results:
                result.case_results = [self._case_result(suite, case, passed=False, blocked=True,
                    error_message=result.error_message, failure_type=result.failure_type) for case in selected]
        finally:
            try:
                if context is not None:
                    try:
                        self._run_steps(suite.teardown, suite.variables, keywords, result.teardown_steps, context, continue_on_failure=True)
                    finally:
                        self._close(context, result.teardown_steps)
            finally:
                result.stop = _now_ms()
                self.last_result = result
        return result

    def _case_result(self, suite, case, **kwargs):
        return CaseResult(name=case.name, suite=suite.name, module=case.module, type=case.type,
                          priority=case.priority, owner=case.owner, tags=list(case.tags), **kwargs)

    def _run_case(self, suite, case, keywords, secrets):
        history = []
        started = _now_ms()
        interrupted = False
        case_dir = self.output_dir / "cases" / uuid4().hex if self.output_dir else None
        for attempt in range(1, case.retry + 2):
            attempt_started = _now_ms()
            steps = []
            context = None
            variables = {**suite.variables, **case.variables}
            try:
                try:
                    context = self._context(suite, secrets, case_dir / f"attempt-{attempt}" if case_dir else None)
                    setup_ok = self._run_steps(case.setup, variables, keywords, steps, context,
                                               case_attempt=attempt, case_max_retries=case.retry)
                    if setup_ok:
                        self._run_steps(case.steps, variables, keywords, steps, context,
                                        continue_on_failure=case.continue_on_failure,
                                        case_attempt=attempt, case_max_retries=case.retry)
                except Exception as exc:
                    redactor = context.redactor if context else Redactor()
                    redactor.secrets.update(secrets)
                    steps.append(StepResult("Execution", False, error_message=redactor.redact(str(exc)),
                                            failure_type=_classify_failure(exc), case_attempt=attempt, case_max_retries=case.retry))
                finally:
                    if context is not None:
                        try:
                            self._run_steps(case.teardown, variables, keywords, steps, context, continue_on_failure=True,
                                            case_attempt=attempt, case_max_retries=case.retry)
                        finally:
                            self._close(context, steps, attempt, case.retry)
            except KeyboardInterrupt:
                interrupted = True
                timestamp = _now_ms()
                steps.append(StepResult("Interrupted", False, error_message="Run interrupted", failure_type="action",
                    case_attempt=attempt, case_max_retries=case.retry, start=timestamp, stop=timestamp))
            passed = all(step.passed for step in steps)
            history.append(CaseAttempt(attempt, passed, steps, _first_error(steps), _first_failure_type(steps),
                                       start=attempt_started, stop=_now_ms()))
            if passed or interrupted:
                break
        final = history[-1]
        result = self._case_result(suite, case, passed=final.passed, step_results=final.steps,
            error_message=final.error_message, failure_type=final.failure_type, attempts=history,
            start=started, stop=_now_ms())
        if interrupted:
            raise _CaseInterrupted(result)
        return result

    def _close(self, context, steps, case_attempt=1, case_max_retries=0):
        if not context.registry.cleanup:
            return
        try:
            context.registry.cleanup()
        except Exception as exc:
            steps.append(StepResult("Close Resources", False, error_message=context.redactor.redact(str(exc)),
                failure_type="action", case_attempt=case_attempt, case_max_retries=case_max_retries))

    def _prepare(self, step, variables, context, keywords):
        try:
            args = interpolate(step.args, variables)
            kwargs = interpolate(step.kwargs, variables)
            context.redactor.collect({"keyword": step.keyword, "args": args, "kwargs": kwargs,
                                      "sensitive_args": step.sensitive_args})
            context.redactor.collect(kwargs)
            for index in step.sensitive_args:
                if index >= len(args):
                    raise DslValidationError("sensitive_args index is outside args")
                context.redactor.add(args[index])
            if normalize_keyword_name(step.keyword) in keywords:
                if args or kwargs or step.timeout is not None or step.sensitive_args:
                    raise DslValidationError("Composite keywords do not accept args, kwargs or timeout")
                return args, kwargs, None
            if step.timeout is not None:
                if "timeout" in kwargs:
                    raise DslValidationError("timeout must be supplied only once")
                kwargs["timeout"] = seconds(interpolate(step.timeout, variables))
            bound = context.registry.bind(step.keyword, args, kwargs, redactor=context.redactor)
            context.redactor.collect(bound.arguments)
            if normalize_keyword_name(step.keyword) == "type text" and sensitive_key(str(bound.arguments.get("locator", ""))):
                context.redactor.add(bound.arguments.get("text"))
            if "timeout" in bound.arguments:
                kwargs["timeout"] = bound.arguments["timeout"]
            elif "kwargs" in bound.arguments:
                kwargs = bound.arguments["kwargs"]
            return args, kwargs, bound
        except (TypeError, ValueError) as exc:
            if isinstance(exc, DslValidationError):
                raise
            raise DslValidationError(str(exc)) from exc

    def _run_steps(self, steps, variables, keywords, results, context, *, continue_on_failure=False,
                   call_chain=(), case_attempt=1, case_max_retries=0):
        passed = True
        for step in steps:
            chain = (*call_chain, step.keyword)
            result = self._run_step(step, variables, keywords, context, chain,
                                    case_attempt, case_max_retries, continue_on_failure)
            results.append(result)
            if not result.passed:
                passed = False
                if not (continue_on_failure or step.continue_on_failure):
                    break
        return passed

    def _run_step(self, step, variables, keywords, context, chain, case_attempt, case_max_retries, continue_on_failure):
        result = StepResult(step.keyword, False, dry_run=self.dry_run, call_chain=list(chain),
                            retry_max_retries=step.retry, case_attempt=case_attempt, case_max_retries=case_max_retries,
                            start=_now_ms())
        started = time.perf_counter()
        try:
            args, kwargs, bound = self._prepare(step, variables, context, keywords)
            result.arguments = context.redactor.redact_values(args)
            for index in step.sensitive_args:
                result.arguments[index] = "***"
            result.kwargs = context.redactor.redact_values(kwargs)
        except Exception as exc:
            result.error_message = context.redactor.redact(str(exc))
            result.failure_type = _classify_failure(exc)
            result.stop = _now_ms()
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            return result
        for attempt in range(1, step.retry + 2):
            result.retry_attempt = attempt
            result.children = []
            attempt_started = time.perf_counter()
            try:
                normalized = normalize_keyword_name(step.keyword)
                if normalized in keywords:
                    result.passed = self._run_steps(keywords[normalized], variables, keywords, result.children, context,
                        continue_on_failure=continue_on_failure or step.continue_on_failure, call_chain=chain,
                        case_attempt=case_attempt, case_max_retries=case_max_retries)
                    result.error_message = _first_error(result.children)
                    result.failure_type = _first_failure_type(result.children)
                else:
                    if not self.dry_run:
                        definition = context.registry.get(step.keyword)
                        if normalized == "screenshot" and context.output_dir is not None:
                            requested = Path(bound.arguments["path"])
                            if not requested.is_absolute():
                                target = (context.output_dir / requested).resolve()
                                if not target.is_relative_to(context.output_dir.resolve()):
                                    raise DslValidationError("Screenshot path must stay inside the run directory")
                                bound.arguments["path"] = str(target)
                        definition.func(*bound.args, **bound.kwargs)
                        if normalized == "screenshot":
                            target = Path(bound.arguments["path"])
                            if target.is_file():
                                result.attachments.append({"name": target.name, "source": str(target.resolve()),
                                                           "type": "image/png"})
                    result.passed = True
                    result.error_message = result.failure_type = None
            except Exception as exc:
                result.error_message = context.redactor.redact(str(exc))
                result.failure_type = _classify_failure(exc)
            if result.passed:
                break
            result.retry_trace.append({"attempt": attempt, "status": "failed", "error": result.error_message,
                "duration_ms": int((time.perf_counter() - attempt_started) * 1000),
                "children": [child.to_dict() for child in result.children]})
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        result.stop = _now_ms()
        # 诊断不能影响动作结果或触发重试。
        try:
            if bound is not None and "locator" in bound.arguments:
                raw = bound.arguments["locator"]
                locator = parse_locator(raw)
                result.resolved_locator = context.redactor.redact({"raw": raw, "by": locator.by, "value": locator.value})
            if context.registry.diagnostics:
                result.current_url = context.redactor.redact(context.registry.diagnostics().get("current_url"))
        except Exception as exc:
            result.diagnostic_error = context.redactor.redact(str(exc))
        return result


def _classify_failure(exc):
    if isinstance(exc, DslValidationError):
        return "validation"
    if isinstance(exc, AssertionError):
        return "assertion"
    return "action"


def _now_ms():
    return time.time_ns() // 1_000_000


def _first_error(steps):
    return next((step.error_message for step in steps if not step.passed), None)


def _first_failure_type(steps):
    return next((step.failure_type for step in steps if not step.passed), None)
