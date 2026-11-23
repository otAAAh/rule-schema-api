# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Describe a rule value from its ValueSpec: a JSON-able node tree.

The REST API's ``value_raw`` is the Python literal of the value as Setup stores
it, which is the valuespec's value space - for legacy rulesets, and for the
FormSpec rulesets Setup can convert to a valuespec. (On 3.0 some cannot; those
go through ``form_spec``.)

Every node is a plain dict:

    {"type": <kind>, "title": str|None, "help": str|None, "valuespec": <class>, ...}

with kind-specific keys (``elements``, ``element``, ``choices``, ``min`` ...).
Unknown valuespec classes become ``{"type": "unknown"}`` with their class name
rather than an error: a third-party MKP may ship any subclass, and the rest of
the tree must still come through.

Internal API: ``cmk.gui.valuespec`` is not a versioned plugin API. Children
are private attributes, read through ``_private``; a drift degrades a node to
less detail instead of failing the request.
"""

from __future__ import annotations

from collections.abc import Mapping

from ._util import (
    call,
    first,
    iterable,
    Json,
    jsonable,
    MAX_CHOICES,
    MAX_DEPTH,
    Node,
    python_literal,
    safe,
    text,
)


def _private(vs: object, name: str) -> object:
    """A valuespec's private attribute: they expose their children no other way."""
    return getattr(vs, name, None)


def _pairs(items: object) -> list[tuple[object, object]]:
    """(value, title) pairs from a choice list, a mapping, or anything else (none)."""
    source = items.items() if isinstance(items, Mapping) else iterable(items)
    pairs: list[tuple[object, object]] = []
    for item in source:
        if isinstance(item, tuple) and len(item) >= 2:
            pairs.append((item[0], item[1]))
    return pairs


def _choices(pairs: list[tuple[object, object]]) -> tuple[list[Json], bool]:
    shown, truncated = first(pairs, MAX_CHOICES)
    return [{"value": jsonable(value), "title": text(title)} for value, title in shown], truncated


def describe_valuespec(vs: object, *, depth: int = 0) -> Node:
    """The node tree for one valuespec."""
    # Imported here: only available inside a Checkmk site's Python.
    from cmk.gui import valuespec as v

    node: Node = {
        "type": "unknown",
        "valuespec": type(vs).__name__,
        "title": text(call(vs, "title")),
        "help": text(call(vs, "help")),
    }
    if depth > MAX_DEPTH:
        node["type"] = "truncated"
        return node

    def child(inner: object) -> Node:
        return describe_valuespec(inner, depth=depth + 1)

    # Order matters: subclasses before their bases (Migrate < Transform,
    # Password < TextInput, Percentage < Float, ...).
    if isinstance(vs, v.Transform):
        inner = child(_private(vs, "_valuespec"))
        # Keep the outer title/help if it has its own.
        inner["title"] = node["title"] or inner["title"]
        inner["help"] = node["help"] or inner["help"]
        # A Migrate only upgrades old values on load; what gets stored is the
        # inner shape. A plain Transform may store something else entirely.
        if not isinstance(vs, v.Migrate):
            inner["transformed"] = True
        return inner

    # The "time-specific parameters" wrapper around nearly every check-parameter
    # ruleset. Lives in watolib, not in cmk.gui.valuespec - matched by name.
    if type(vs).__name__ == "TimeperiodValuespec":
        node.update(
            type="timespecific",
            element=child(_private(vs, "_enclosed_valuespec")),
            default_key="tp_default_value",
            values_key="tp_values",
        )
        return node

    if isinstance(vs, v.ElementSelection):
        # Check plug-in groups, host/service/contact groups, ...: a string out of
        # a set computed from the site's configuration.
        choices, truncated = _choices(_pairs(safe(vs.get_elements, {})))
        node.update(type="choice", choices=choices, truncated=truncated)
        return node

    if isinstance(vs, v.TimeSpan):
        node.update(type="float", unit="seconds")
        _bounds(node, vs)
        return node

    if isinstance(vs, v.TimeofdayRange):
        node.update(type="timeofday_range", format="((hours, minutes), (hours, minutes))")
        return node

    if isinstance(vs, v.Dictionary):
        optional = _private(vs, "_optional_keys")
        required = set(iterable(_private(vs, "_required_keys")))
        hidden = set(iterable(_private(vs, "_hidden_keys")))
        get_elements = _private(vs, "_get_elements")
        raw = safe(get_elements, ()) if callable(get_elements) else ()
        elements: list[Json] = []
        for item in iterable(raw):
            if not (isinstance(item, tuple) and len(item) == 2):
                continue
            key, element_vs = item
            elements.append(
                {
                    "key": str(key),
                    "required": optional is False or key in required,
                    "hidden": key in hidden,
                    "schema": child(element_vs),
                }
            )
        node.update(type="dictionary", elements=elements)
        return node

    if isinstance(vs, v.Tuple):
        node.update(type="tuple", elements=[child(e) for e in iterable(_private(vs, "_elements"))])
        return node

    if isinstance(vs, v.ListOfStrings | v.ListOf):
        node.update(type="list", element=child(_private(vs, "_valuespec")))
        return node

    if isinstance(vs, v.CascadingDropdown):
        shown, truncated = first(safe(vs.choices, []), MAX_CHOICES)
        cascading: list[Json] = [
            {
                "value": jsonable(value),
                "title": text(title),
                "schema": None if sub_vs is None else child(sub_vs),
            }
            for value, title, sub_vs in shown
        ]
        node.update(type="cascading", choices=cascading, truncated=truncated)
        return node

    if isinstance(vs, v.Alternative):
        node.update(
            type="alternative", elements=[child(e) for e in iterable(_private(vs, "_elements"))]
        )
        return node

    if isinstance(vs, v.Optional):
        node.update(type="optional", element=child(_private(vs, "_valuespec")))
        return node

    if isinstance(vs, v.FixedValue):
        node.update(type="fixed", value=jsonable(_private(vs, "_value")))
        return node

    if isinstance(vs, v.DropdownChoice):
        choices, truncated = _choices(_pairs(safe(vs.choices, [])))
        node.update(type="choice", choices=choices, truncated=truncated)
        return node

    if isinstance(vs, v.ListChoice):
        elements_or_none: object = safe(vs.get_elements, None)
        if elements_or_none is None:
            raw_choices = _private(vs, "_choices")
            elements_or_none = safe(raw_choices, []) if callable(raw_choices) else raw_choices
        choices, truncated = _choices(_pairs(elements_or_none))
        node.update(type="multiple_choice", choices=choices, truncated=truncated)
        return node

    if isinstance(vs, v.Checkbox):
        node["type"] = "boolean"
        return node

    if isinstance(vs, v.Integer | v.Age):
        node["type"] = "integer"
        _bounds(node, vs)
        if isinstance(vs, v.Age):
            node["unit"] = "seconds"
        return node

    if isinstance(vs, v.Float):
        node["type"] = "float"
        _bounds(node, vs)
        if isinstance(vs, v.Percentage):
            node["unit"] = "percent"
        return node

    if isinstance(vs, v.TextInput):
        node["type"] = "string"
        if isinstance(vs, v.Password):
            node["secret"] = True
        if regex := _private(vs, "_regex"):
            node["pattern"] = str(getattr(regex, "pattern", regex))
        return node

    if isinstance(vs, v.Labels):
        node["type"] = "labels"
        return node

    return node


def _bounds(node: Node, vs: object) -> None:
    bounds = _private(vs, "_bounds")
    for key, attr in (("min", "_lower"), ("max", "_upper")):
        limit = getattr(bounds, attr, None)
        if isinstance(limit, int | float):
            node[key] = limit


def example_value_raw(vs: object) -> str | None:
    """A valid ``value_raw`` to start from: the valuespec's default value."""
    default_value = getattr(vs, "default_value", None)
    if not callable(default_value):
        return None
    try:
        return python_literal(default_value())
    except Exception:
        return None
