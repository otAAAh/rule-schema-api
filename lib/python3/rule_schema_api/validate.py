# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Validate a ``value_raw`` exactly like the rules API does, without creating a rule.

The rules API (``POST /domain-types/rule/collections/all``) checks a rule's value
with one function: the FormSpec visitor where the ruleset has a FormSpec, else
the valuespec, and in both cases it rejects a value in an outdated format.
This module calls that same function, so "valid" here means "the rules API
accepts this value" - for the value; the folder, conditions and permissions of
a real rule are not part of it.

The function is internal and moved between releases:

    3.0  cmk.gui.openapi.api_endpoints.rule._utils.validate_value
    2.5  cmk.gui.openapi.endpoints.rule._validate_value

Both take the ruleset (only its ``rulespec`` is used) and raise an exception
with ``title`` and ``detail`` - the problem body the rules API would answer with.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from types import SimpleNamespace

type Problem = dict[str, str]


def _rules_api_validator() -> Callable[[object, object], None] | None:
    """The rules API's own value check, or None if this Checkmk has neither."""
    try:
        from cmk.gui.openapi.api_endpoints.rule._utils import validate_value

        return validate_value  # type: ignore[return-value, unused-ignore]
    except ImportError:
        pass
    try:  # 2.5. Type-checked against 3.0, where this module does not exist.
        from cmk.gui.openapi.endpoints.rule import (  # type: ignore[attr-defined, import-not-found, import-untyped, unused-ignore]
            _validate_value,
        )
    except ImportError:
        return None
    validator: Callable[[object, object], None] = _validate_value
    return validator


def parse_value_raw(value_raw: str) -> object:
    """``value_raw`` as the rules API reads it: a Python literal."""
    return ast.literal_eval(value_raw)


def validate_value_raw(rulespec: object, value_raw: str) -> list[Problem] | None:
    """The problems the rules API would report for this value; [] means valid.

    None means this Checkmk offers no validator to call (an unknown release).
    """
    try:
        value = parse_value_raw(value_raw)
    except (SyntaxError, ValueError) as exc:
        return [{"title": "value_raw is not a Python literal", "detail": str(exc)}]
    return validate_value(rulespec, value)


def validate_value(rulespec: object, value: object) -> list[Problem] | None:
    validator = _rules_api_validator()
    if validator is None:
        return None
    try:
        validator(SimpleNamespace(rulespec=rulespec), value)
    except Exception as exc:
        title = getattr(exc, "title", None) or getattr(exc, "description", None)
        detail = getattr(exc, "detail", None)
        if isinstance(title, str):
            return [{"title": title, "detail": str(detail or "")}]
        # The validator itself failed: the rules API would answer HTTP 500.
        return [
            {
                "title": "The value check failed with an internal error",
                "detail": f"{type(exc).__name__}: {exc}",
            }
        ]
    return []
