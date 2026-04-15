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
    ("expression", "error_pattern"),
    [
        ("", r"Tag expression is empty"),
        (
            "smoke AND OR critical",
            r"unexpected token 'OR' at position 10; expected TAG, NOT, LPAREN",
        ),
        (
            "smoke AND (critical OR)",
            r"unexpected token '\)' at position 22; expected TAG, NOT, LPAREN",
        ),
        ("NOT", r"unexpected end of expression at position 3; expected TAG, NOT, LPAREN"),
        ("(smoke OR critical", r"unexpected end of expression at position 18; expected RPAREN"),
        ("smoke)", r"unexpected token '\)' at position 5; expected end of expression"),
    ],
)
def test_tag_expression_invalid_syntax(expression: str, error_pattern: str) -> None:
    with pytest.raises(ValueError, match=error_pattern):
        compile_tag_expression(expression)
