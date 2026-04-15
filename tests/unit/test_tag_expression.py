import pytest

from framework.executor.tag_expression import compile_tag_expression


def test_tag_expression_eval_complex() -> None:
    expr = compile_tag_expression("(smoke OR critical) AND NOT flaky")

    assert expr({"smoke", "api"}) is True
    assert expr({"critical", "flaky"}) is False


def test_tag_expression_respects_precedence_without_parentheses() -> None:
    expr = compile_tag_expression("smoke OR critical AND NOT flaky")

    assert expr({"smoke"}) is True
    assert expr({"critical"}) is True
    assert expr({"critical", "flaky"}) is False


def test_tag_expression_matches_tags_case_insensitively() -> None:
    expr = compile_tag_expression("SMOKE and Not FLAKY")

    assert expr({"smoke", "api"}) is True
    assert expr({"Smoke", "Flaky"}) is False


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "smoke AND OR critical",
        "smoke AND (critical OR)",
        "NOT",
        "(smoke OR critical",
        "smoke)",
    ],
)
def test_tag_expression_invalid_syntax(expression: str) -> None:
    with pytest.raises(ValueError):
        compile_tag_expression(expression)
