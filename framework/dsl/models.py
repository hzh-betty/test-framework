from __future__ import annotations

from dataclasses import dataclass, field


Scalar = str | int | float | bool


@dataclass(frozen=True, init=False)
class StepSpec:
    keyword: str
    args: list[Scalar] = field(default_factory=list)
    kwargs: dict[str, Scalar] = field(default_factory=dict)
    timeout: str | int | float | None = None
    retry: int | None = None
    continue_on_failure: bool = False

    def __init__(
        self,
        keyword: str | None = None,
        args: list[Scalar] | None = None,
        kwargs: dict[str, Scalar] | None = None,
        timeout: str | int | float | None = None,
        retry: int | None = None,
        continue_on_failure: bool = False,
        **legacy: object,
    ):
        action = legacy.pop("action", None)
        target = legacy.pop("target", None)
        value = legacy.pop("value", None)
        if legacy:
            unknown = ", ".join(sorted(str(key) for key in legacy))
            raise TypeError(f"Unknown StepSpec field(s): {unknown}")
        resolved_keyword = keyword if keyword is not None else _legacy_action_to_keyword(action)
        resolved_args = list(args or [])
        if keyword is None and action is not None:
            resolved_args = _legacy_args(action, target, value)
            if str(action).strip().lower() == "call" and resolved_args:
                resolved_keyword = str(resolved_args[0])
                resolved_args = []
            if str(action).strip().lower() == "accept_alert" and value is not None and timeout is None:
                timeout = value if isinstance(value, (str, int, float)) else str(value)
        object.__setattr__(self, "keyword", resolved_keyword)
        object.__setattr__(self, "args", resolved_args)
        object.__setattr__(self, "kwargs", dict(kwargs or {}))
        object.__setattr__(self, "timeout", timeout)
        object.__setattr__(self, "retry", retry)
        object.__setattr__(self, "continue_on_failure", continue_on_failure)

    @property
    def action(self) -> str:
        return _keyword_to_legacy_action(self.keyword)

    @property
    def target(self) -> str | None:
        if not self.args:
            return None
        value = self.args[0]
        return value if isinstance(value, str) else str(value)

    @property
    def value(self) -> str | None:
        if len(self.args) < 2:
            return None
        value = self.args[1]
        return value if isinstance(value, str) else str(value)


_ACTION_TO_KEYWORD = {
    "open": "Open",
    "click": "Click",
    "type": "Type Text",
    "clear": "Clear",
    "assert_text": "Assert Text",
    "wait_visible": "Wait Visible",
    "wait_not_visible": "Wait Not Visible",
    "wait_gone": "Wait Gone",
    "wait_clickable": "Wait Clickable",
    "wait_text": "Wait Text",
    "wait_url_contains": "Wait URL Contains",
    "assert_element_visible": "Assert Element Visible",
    "assert_element_contains": "Assert Element Contains",
    "assert_url_contains": "Assert URL Contains",
    "assert_title_contains": "Assert Title Contains",
    "select": "Select",
    "hover": "Hover",
    "switch_frame": "Switch Frame",
    "switch_window": "Switch Window",
    "accept_alert": "Accept Alert",
    "upload_file": "Upload File",
    "screenshot": "Screenshot",
    "new_browser": "New Browser",
    "switch_browser": "Switch Browser",
    "close_browser": "Close Browser",
}
_KEYWORD_TO_ACTION = {keyword.casefold(): action for action, keyword in _ACTION_TO_KEYWORD.items()}


def _legacy_action_to_keyword(action: object) -> str:
    if not isinstance(action, str) or not action.strip():
        raise TypeError("StepSpec requires keyword.")
    return _ACTION_TO_KEYWORD.get(action.strip().lower(), action)


def _legacy_args(action: object, target: object, value: object) -> list[Scalar]:
    if str(action).strip().lower() == "accept_alert":
        return []
    args: list[Scalar] = []
    if target is not None:
        args.append(target if isinstance(target, (str, int, float, bool)) else str(target))
    if value is not None:
        args.append(value if isinstance(value, (str, int, float, bool)) else str(value))
    return args


def _keyword_to_legacy_action(keyword: str) -> str:
    return _KEYWORD_TO_ACTION.get(keyword.casefold(), keyword)


@dataclass(frozen=True)
class CaseSpec:
    name: str
    setup: list[StepSpec] = field(default_factory=list)
    steps: list[StepSpec] = field(default_factory=list)
    teardown: list[StepSpec] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    retry: int | None = None
    continue_on_failure: bool = False


@dataclass(frozen=True)
class SuiteSpec:
    name: str
    setup: list[StepSpec] = field(default_factory=list)
    cases: list[CaseSpec] = field(default_factory=list)
    teardown: list[StepSpec] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    keywords: dict[str, list[StepSpec]] = field(default_factory=dict)
