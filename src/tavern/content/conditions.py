from __future__ import annotations

import re

_CONDITION_PATTERN = re.compile(
    r"^(turn)\s*(>|<|>=|<=|==|!=)\s*(\d+)$"
)

_OPERATORS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def evaluate_content_condition(when: str, *, turn: int = 0, **kwargs: object) -> bool:
    """Evaluate a simple content condition expression.

    Supports: 'turn > N', 'turn < N', 'turn >= N', 'turn <= N',
              'turn == N', 'turn != N'.

    Returns False for unparseable expressions or unknown variables.
    """
    when = when.strip()
    if not when:
        return False

    match = _CONDITION_PATTERN.match(when)
    if match is None:
        return False

    variable, operator, value_str = match.groups()
    variables = {"turn": turn}

    if variable not in variables:
        return False

    op_fn = _OPERATORS.get(operator)
    if op_fn is None:
        return False

    return op_fn(variables[variable], int(value_str))
