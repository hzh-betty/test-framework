from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


TagPredicate = Callable[[set[str]], bool]


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    position: int


def _tokenize(expression: str) -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    while i < len(expression):
        char = expression[i]
        if char.isspace():
            i += 1
            continue
        if char == "(":
            tokens.append(_Token("LPAREN", char, i))
            i += 1
            continue
        if char == ")":
            tokens.append(_Token("RPAREN", char, i))
            i += 1
            continue

        start = i
        while i < len(expression) and (not expression[i].isspace()) and expression[i] not in "()":
            i += 1
        word = expression[start:i]
        upper = word.upper()
        if upper in {"AND", "OR", "NOT"}:
            tokens.append(_Token(upper, upper, start))
        else:
            tokens.append(_Token("TAG", word.lower(), start))

    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token], expression_length: int):
        self._tokens = tokens
        self._position = 0
        self._expression_length = expression_length

    def parse(self) -> TagPredicate:
        if not self._tokens:
            raise ValueError("Tag expression is empty")

        predicate = self._parse_or()
        if self._peek() is not None:
            self._raise_syntax_error("end of expression")
        return predicate

    def _parse_or(self) -> TagPredicate:
        left = self._parse_and()
        while self._match("OR"):
            right = self._parse_and()
            current = left
            left = lambda tags, a=current, b=right: a(tags) or b(tags)
        return left

    def _parse_and(self) -> TagPredicate:
        left = self._parse_not()
        while self._match("AND"):
            right = self._parse_not()
            current = left
            left = lambda tags, a=current, b=right: a(tags) and b(tags)
        return left

    def _parse_not(self) -> TagPredicate:
        token = self._peek()
        if token is None or token.kind not in {"NOT", "TAG", "LPAREN"}:
            self._raise_syntax_error("TAG, NOT, LPAREN")
        if self._match("NOT"):
            operand = self._parse_not()
            return lambda tags: not operand(tags)
        return self._parse_primary()

    def _parse_primary(self) -> TagPredicate:
        if self._match("LPAREN"):
            inner = self._parse_or()
            if not self._match("RPAREN"):
                self._raise_syntax_error("RPAREN")
            return inner

        token = self._peek()
        if token is None or token.kind != "TAG":
            self._raise_syntax_error("TAG")

        self._position += 1
        return lambda tags, expected=token.value: expected in tags

    def _peek(self) -> _Token | None:
        if self._position >= len(self._tokens):
            return None
        return self._tokens[self._position]

    def _match(self, kind: str) -> bool:
        token = self._peek()
        if token is None or token.kind != kind:
            return False
        self._position += 1
        return True

    def _raise_syntax_error(self, expected: str) -> None:
        token = self._peek()
        if token is None:
            raise ValueError(
                f"Invalid tag expression syntax: unexpected end of expression at position "
                f"{self._expression_length}; expected {expected}"
            )
        raise ValueError(
            f"Invalid tag expression syntax: unexpected token '{token.value}' at position "
            f"{token.position}; expected {expected}"
        )


def compile_tag_expression(expression: str) -> Callable[[set[str]], bool]:
    parser = _Parser(_tokenize(expression), len(expression))
    predicate = parser.parse()

    def evaluate(tags: set[str]) -> bool:
        normalized_tags = {tag.lower() for tag in tags}
        return predicate(normalized_tags)

    return evaluate
