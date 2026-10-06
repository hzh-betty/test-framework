"""筛选表达式在遍历用例前解析一次；语法错误不能当作不匹配。"""

from webtest_core.dsl import CaseSpec, DslValidationError


def parse_tag_expression(expression: str | None):
    if expression is None:
        return None
    tokens = expression.replace("(", " ( ").replace(")", " ) ").casefold().split()
    position = 0

    def take(token):
        nonlocal position
        if position < len(tokens) and tokens[position] == token:
            position += 1
            return True
        return False

    def atom():
        nonlocal position
        if take("not"):
            return ("not", atom())
        if take("("):
            node = disjunction()
            if not take(")"):
                raise DslValidationError("Tag expression requires a closing parenthesis")
            return node
        if position >= len(tokens) or tokens[position] in {"and", "or", ")"}:
            raise DslValidationError("Tag expression requires a tag")
        tag = tokens[position]
        position += 1
        return ("tag", tag)

    def conjunction():
        node = atom()
        while take("and"):
            node = ("and", node, atom())
        return node

    def disjunction():
        node = conjunction()
        while take("or"):
            node = ("or", node, conjunction())
        return node

    node = disjunction()
    if position != len(tokens):
        raise DslValidationError(f"Unexpected tag expression token: {tokens[position]}")
    return node


def matches(tags: list[str], node) -> bool:
    tag_set = {tag.casefold() for tag in tags}

    def evaluate(node):
        operator, *operands = node
        if operator == "tag":
            return operands[0] in tag_set
        if operator == "not":
            return not evaluate(operands[0])
        if operator == "and":
            return evaluate(operands[0]) and evaluate(operands[1])
        return evaluate(operands[0]) or evaluate(operands[1])

    return evaluate(node)


def select_cases(cases: list[CaseSpec], *, include_tag_expr=None, exclude_tag_expr=None,
                 modules=None, case_types=None, priorities=None, owners=None, allowed_case_names=None) -> list[CaseSpec]:
    include = parse_tag_expression(include_tag_expr)
    exclude = parse_tag_expression(exclude_tag_expr)
    selected = []
    for case in cases:
        if allowed_case_names is not None and case.name not in allowed_case_names:
            continue
        if any(values is not None and (getattr(case, field) or "") not in values
               for field, values in (("module", modules), ("type", case_types), ("priority", priorities), ("owner", owners))):
            continue
        if include is not None and not matches(case.tags, include):
            continue
        if exclude is not None and matches(case.tags, exclude):
            continue
        selected.append(case)
    return selected
