from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
import re

from framework.core.time import parse_positive_timeout
from framework.dsl.models import StepSpec


class ActionValidationError(ValueError):
    """Raised when an action name or arguments are invalid."""


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    method: str
    requires_target: bool = True
    requires_value: bool = False
    value_argument: bool = False
    timeout_argument: bool = False
    target_from_value: bool = False
    target_argument: bool = True


class ActionRegistry:
    def __init__(self, definitions: list[ActionDefinition]):
        self._definitions = {definition.name: definition for definition in definitions}

    @property
    def action_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def dispatch(self, page: object, step: StepSpec) -> None:
        action = normalize_action_name(step.action)
        definition = self._definitions.get(action)
        if definition is None:
            raise ActionValidationError(self._unknown_action_message(step.action, action))
        target = step.target
        value = step.value
        if definition.target_from_value and target is None:
            target = value
        if definition.requires_target and not target:
            raise ActionValidationError(f"Action '{definition.name}' requires target.")
        if definition.requires_value and value is None:
            raise ActionValidationError(f"Action '{definition.name}' requires value.")

        method = getattr(page, definition.method)
        args = []
        kwargs = {}
        if target is not None and definition.target_argument:
            args.append(target)
        if definition.value_argument:
            args.append(value)
        if definition.timeout_argument:
            timeout_value = step.timeout
            if timeout_value is None and not definition.value_argument and step.value is not None:
                timeout_value = step.value
            kwargs["timeout"] = parse_positive_timeout(timeout_value or 10)
        method(*args, **kwargs)

    def _unknown_action_message(self, raw_action: str, normalized_action: str) -> str:
        matches = get_close_matches(normalized_action, self.action_names, n=3)
        if matches:
            return f"Unknown action '{raw_action}'. Did you mean: {', '.join(matches)}?"
        return f"Unknown action '{raw_action}'. Supported actions: {', '.join(self.action_names)}."


def normalize_action_name(name: str) -> str:
    normalized = re.sub(r"[\s\-]+", "_", name.strip().casefold())
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def default_action_registry() -> ActionRegistry:
    return ActionRegistry(
        [
            ActionDefinition("open", "open"),
            ActionDefinition("click", "click"),
            ActionDefinition("type", "type", requires_value=True, value_argument=True),
            ActionDefinition(
                "clear",
                "clear",
            ),
            ActionDefinition(
                "assert_text",
                "assert_text",
                requires_value=True,
                value_argument=True,
            ),
            ActionDefinition(
                "wait_visible",
                "wait_visible",
                timeout_argument=True,
            ),
            ActionDefinition(
                "wait_not_visible",
                "wait_not_visible",
                timeout_argument=True,
            ),
            ActionDefinition(
                "wait_gone",
                "wait_gone",
                timeout_argument=True,
            ),
            ActionDefinition(
                "wait_clickable",
                "wait_clickable",
                timeout_argument=True,
            ),
            ActionDefinition(
                "wait_text",
                "wait_text",
                requires_value=True,
                value_argument=True,
                timeout_argument=True,
            ),
            ActionDefinition(
                "wait_url_contains",
                "wait_url_contains",
                timeout_argument=True,
            ),
            ActionDefinition(
                "assert_element_visible",
                "assert_element_visible",
                timeout_argument=True,
            ),
            ActionDefinition(
                "assert_element_contains",
                "assert_element_contains",
                requires_value=True,
                value_argument=True,
            ),
            ActionDefinition(
                "assert_url_contains",
                "assert_url_contains",
            ),
            ActionDefinition(
                "assert_title_contains",
                "assert_title_contains",
            ),
            ActionDefinition("select", "select", requires_value=True, value_argument=True),
            ActionDefinition("hover", "hover"),
            ActionDefinition("switch_frame", "switch_frame"),
            ActionDefinition("switch_window", "switch_window"),
            ActionDefinition(
                "accept_alert",
                "accept_alert",
                requires_target=False,
                timeout_argument=True,
                target_argument=False,
            ),
            ActionDefinition(
                "upload_file",
                "upload_file",
                requires_value=True,
                value_argument=True,
            ),
            ActionDefinition(
                "screenshot",
                "screenshot",
                requires_target=False,
                target_from_value=True,
            ),
            ActionDefinition("new_browser", "new_browser", requires_target=False),
            ActionDefinition("switch_browser", "switch_browser"),
            ActionDefinition("close_browser", "close_browser", requires_target=False),
        ]
    )
