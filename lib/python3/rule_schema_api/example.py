# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""An example ``value_raw`` built from a schema node tree.

The smallest value the schema allows: required keys only, the first real
choice, numbers at their minimum - and placeholders where an empty value would
be rejected (a required text, a URL, an e-mail address). The catalog validates
it with the rules API's own check before handing it out.
"""

from __future__ import annotations

from ._util import Json, MAX_DEPTH


def _nodes(value: Json) -> list[dict[str, Json]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _number(value: Json) -> int | float | None:
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _first_choice(node: dict[str, Json]) -> dict[str, Json] | None:
    """The first choice that is a real selection (not the "please select" None)."""
    choices = _nodes(node.get("choices"))
    real = [c for c in choices if c.get("value") is not None]
    if real:
        return real[0]
    return choices[0] if choices else None


def _text_example(node: dict[str, Json]) -> str:
    match node.get("format"):
        case "url":
            protocols = node.get("protocols")
            scheme = protocols[0] if isinstance(protocols, list) and protocols else "https"
            return f"{scheme}://example.com"
        case "email":
            return "user@example.com"
        case _:
            pass
    min_length = _number(node.get("min_length"))
    if min_length is None or min_length <= 0:
        return ""
    return "example".ljust(int(min_length), "x")


def example_from_node(node: Json, *, depth: int = 0) -> object:
    """A minimal value matching ``node``; see the module docstring."""
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
        case "list":
            min_items = _number(node.get("min_items"))
            return [sub(node.get("element"))] * int(min_items) if min_items else []
        case "multiple_choice":
            # One selected entry: several rulesets reject an empty selection
            # with a validator of their own that the schema cannot show.
            choice = _first_choice(node)
            return [] if choice is None else [choice.get("value")]
        case "labels":
            return {}
        case "timespecific":
            return sub(node.get("element"))
        case "optional":
            return None
        case "cascading":
            choice = _first_choice(node)
            if choice is None:
                return None
            schema = choice.get("schema")
            return (choice.get("value"), None if schema is None else sub(schema))
        case "choice":
            choice = _first_choice(node)
            return None if choice is None else choice.get("value")
        case "fixed":
            return node.get("value")
        case "alternative":
            elements = _nodes(node.get("elements"))
            return sub(elements[0]) if elements else None
        case "integer":
            low = _number(node.get("min"))
            return int(low) if low is not None else 0
        case "float":
            low = _number(node.get("min"))
            return float(low) if low is not None else 0.0
        case "boolean":
            return False
        case "string":
            return _text_example(node)
        case "password":
            return ("cmk_postprocessed", "explicit_password", ("<id>", "<password>"))
        case "proxy":
            return ("cmk_postprocessed", "environment_proxy", "")
        case "time_period":
            return ("cmk_postprocessed", "stored_time_period", "24X7")
        case "oauth2_connection":
            return ("cmk_postprocessed", "oauth2_connection", "<connection id>")
        case _:
            return None
