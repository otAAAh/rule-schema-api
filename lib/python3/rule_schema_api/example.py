# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""An example ``value_raw`` built from a schema node tree."""

from __future__ import annotations

from ._util import Json, MAX_DEPTH


def _nodes(value: Json) -> list[dict[str, Json]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def example_from_node(node: Json, *, depth: int = 0) -> object:
    """A minimal value matching ``node``: required keys only, first choices, zeros.

    For FormSpec rulesets, which have no valuespec ``default_value()``. It shows
    the shape; bounds and validators may still reject the zeros.
    """
    if depth > MAX_DEPTH or not isinstance(node, dict):
        return None
    kind = node.get("type")

    def sub(inner: Json) -> object:
        return example_from_node(inner, depth=depth + 1)

    match kind:
        case "dictionary":
            return {
                str(e.get("key")): sub(e.get("schema"))
                for e in _nodes(node.get("elements"))
                if e.get("required") is True
            }
        case "tuple":
            return tuple(sub(e) for e in _nodes(node.get("elements")))
        case "list" | "multiple_choice":
            return []
        case "labels":
            return {}
        case "timespecific":
            return sub(node.get("element"))
        case "optional":
            return None
        case "cascading":
            choices = _nodes(node.get("choices"))
            if not choices:
                return None
            schema = choices[0].get("schema")
            return (choices[0].get("value"), None if schema is None else sub(schema))
        case "choice":
            choices = _nodes(node.get("choices"))
            return choices[0].get("value") if choices else None
        case "fixed":
            return node.get("value")
        case "alternative":
            elements = _nodes(node.get("elements"))
            return sub(elements[0]) if elements else None
        case "integer":
            low = node.get("min")
            return low if isinstance(low, int) and not isinstance(low, bool) else 0
        case "float":
            low = node.get("min")
            return float(low) if isinstance(low, int | float) and not isinstance(low, bool) else 0.0
        case "boolean":
            return False
        case "string":
            return ""
        case "password":
            return ("cmk_postprocessed", "explicit_password", ("<id>", "<password>"))
        case _:
            return None
