# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Describe a rule value's shape: turn a ValueSpec tree into a JSON-able node tree.

Why the *valuespec*, not the FormSpec: the REST API's ``value_raw`` is the
Python literal of the value as Setup stores it, and that is the valuespec's
value space for every ruleset - legacy ones, and FormSpec ones too (Setup
converts those to a valuespec). So one walker covers all rulesets and describes
exactly what ``value_raw`` accepts.

Every node is a plain dict:

    {"type": <kind>, "title": str|None, "help": str|None, "valuespec": <class>, ...}

with kind-specific keys (``elements``, ``element``, ``choices``, ``min`` ...).
Unknown valuespec classes become ``{"type": "unknown"}`` with their class name
rather than an error: a third-party MKP may ship any subclass, and the explorer
must still render the rest of the tree.

Internal API: ``cmk.gui.valuespec`` is not a versioned plugin API. Its private
attributes are read with ``getattr`` defaults, so a drift degrades a node to
less detail instead of breaking the page.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

# Choice lists can be huge (all host groups, all timeperiods, ...) and some are
# computed from live config. The explorer shows the first ones and says so.
MAX_CHOICES = 200
# Valuespec trees are finite, but a buggy third-party one could recurse.
MAX_DEPTH = 40

type Node = dict[str, Any]

_TAG_RE = re.compile(r"<[^>]+>")


def _text(value: object) -> str | None:
    """A title/help as plain text (HTML objects and tags flattened)."""
    if value is None:
        return None
    text = _TAG_RE.sub("", str(value)).strip()
    return text or None


def _safe(fn: Callable[[], Any], default: Any = None) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001 - live-config lookups may fail in many ways
        return default


def python_literal(value: object) -> str:
    """The value as a ``value_raw`` string (the REST API takes a Python literal)."""
    return repr(value)


def _first(items: Iterable[Any], limit: int) -> tuple[list[Any], bool]:
    """The first ``limit`` items, and whether there were more."""
    result: list[Any] = []
    for item in items:
        if len(result) == limit:
            return result, True
        result.append(item)
    return result, False


def describe(vs: Any, *, depth: int = 0) -> Node:
    """The node tree for one valuespec."""
    # Imported here: only available inside a Checkmk site's Python.
    from cmk.gui import valuespec as v

    node: Node = {
        "type": "unknown",
        "valuespec": type(vs).__name__,
        "title": _text(_safe(vs.title)),
        "help": _text(_safe(vs.help)),
    }
    if depth > MAX_DEPTH:
        node["type"] = "truncated"
        return node

    def child(inner: Any) -> Node:
        return describe(inner, depth=depth + 1)

    # Order matters: subclasses before their bases (Migrate < Transform,
    # Password < TextInput, Percentage < Float, ...).
    if isinstance(vs, v.Transform):
        inner = vs._valuespec
        node.update(child(inner))
        # Keep the outer title/help if it has its own.
        node["title"] = _text(_safe(vs.title)) or node["title"]
        node["help"] = _text(_safe(vs.help)) or node["help"]
        # A Migrate only upgrades old values on load; what gets stored is the
        # inner shape. A plain Transform may store something else entirely.
        if not isinstance(vs, v.Migrate):
            node["transformed"] = True
        return node

    # The "time-specific parameters" wrapper around nearly every check-parameter
    # ruleset. Lives in watolib, not in cmk.gui.valuespec - matched by name.
    if type(vs).__name__ == "TimeperiodValuespec":
        node.update(
            type="timespecific",
            element=child(vs._enclosed_valuespec),
            default_key="tp_default_value",
            values_key="tp_values",
        )
        return node

    if isinstance(vs, v.ElementSelection):
        # Check plug-in groups, host/service/contact groups, ...: a string out of
        # a set computed from the site's configuration.
        elements = _safe(vs.get_elements, {}) or {}
        choices, truncated = _first(elements.items(), MAX_CHOICES)
        node.update(
            type="choice",
            choices=[{"value": _jsonable(key), "title": _text(title)} for key, title in choices],
            truncated=truncated,
        )
        return node

    if isinstance(vs, v.TimeSpan):
        node.update(type="float", unit="seconds")
        _bounds(node, vs)
        return node

    if isinstance(vs, v.TimeofdayRange):
        node.update(type="timeofday_range", format="((hours, minutes), (hours, minutes))")
        return node

    if isinstance(vs, v.Dictionary):
        optional = getattr(vs, "_optional_keys", True)
        required = set(getattr(vs, "_required_keys", []) or [])
        hidden = set(getattr(vs, "_hidden_keys", []) or [])
        elements = []
        for key, element_vs in _safe(lambda: list(vs._get_elements()), []):
            elements.append(
                {
                    "key": key,
                    "required": optional is False or key in required,
                    "hidden": key in hidden,
                    "schema": child(element_vs),
                }
            )
        node.update(type="dictionary", elements=elements)
        return node

    if isinstance(vs, v.Tuple):
        node.update(type="tuple", elements=[child(e) for e in getattr(vs, "_elements", [])])
        return node

    if isinstance(vs, v.ListOfStrings):
        node.update(type="list", element=child(vs._valuespec))
        return node

    if isinstance(vs, v.ListOf):
        node.update(type="list", element=child(vs._valuespec))
        return node

    if isinstance(vs, v.CascadingDropdown):
        choices, truncated = _first(_safe(vs.choices, []), MAX_CHOICES)
        node.update(
            type="cascading",
            choices=[
                {
                    "value": _jsonable(value),
                    "title": _text(title),
                    "schema": None if sub_vs is None else child(sub_vs),
                }
                for value, title, sub_vs in choices
            ],
            truncated=truncated,
        )
        return node

    if isinstance(vs, v.Alternative):
        node.update(type="alternative", elements=[child(e) for e in getattr(vs, "_elements", [])])
        return node

    if isinstance(vs, v.Optional):
        node.update(type="optional", element=child(vs._valuespec))
        return node

    if isinstance(vs, v.FixedValue):
        node.update(type="fixed", value=_jsonable(getattr(vs, "_value", None)))
        return node

    if isinstance(vs, v.DropdownChoice):
        choices, truncated = _first(_safe(vs.choices, []), MAX_CHOICES)
        node.update(
            type="choice",
            choices=[{"value": _jsonable(c[0]), "title": _text(c[1])} for c in choices],
            truncated=truncated,
        )
        return node

    if isinstance(vs, v.ListChoice):
        elements = _safe(lambda: vs.get_elements(), None)
        if elements is None:
            raw = getattr(vs, "_choices", [])
            elements = _safe(raw, []) if callable(raw) else raw
        items = elements.items() if isinstance(elements, dict) else elements
        choices, truncated = _first(items, MAX_CHOICES)
        node.update(
            type="multiple_choice",
            choices=[{"value": _jsonable(c[0]), "title": _text(c[1])} for c in choices],
            truncated=truncated,
        )
        return node

    if isinstance(vs, v.Checkbox):
        node["type"] = "boolean"
        return node

    if isinstance(vs, (v.Integer, v.Age)):
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
        if regex := getattr(vs, "_regex", None):
            node["pattern"] = getattr(regex, "pattern", str(regex))
        return node

    if isinstance(vs, v.Labels):
        node["type"] = "labels"
        return node

    return node


def _bounds(node: Node, vs: Any) -> None:
    bounds = getattr(vs, "_bounds", None)
    if bounds is None:
        return
    if (lower := getattr(bounds, "_lower", None)) is not None:
        node["min"] = lower
    if (upper := getattr(bounds, "_upper", None)) is not None:
        node["max"] = upper


def _jsonable(value: object) -> object:
    """Choice values are arbitrary Python; keep JSON scalars, repr the rest."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return python_literal(value)


def example_value_raw(vs: Any) -> str | None:
    """A valid ``value_raw`` to start from: the valuespec's default value."""
    value = _safe(vs.default_value, _MISSING)
    if value is _MISSING:
        return None
    return python_literal(value)


_MISSING = object()


# --- FormSpecs ------------------------------------------------------------------
#
# On 3.0 some FormSpec rulesets can no longer be turned into a valuespec
# (``rulespec.valuespec`` raises NotImplementedError), so their schema is read
# from the FormSpec itself. FormSpecs are dataclasses; dispatch is by class name
# along the MRO, so the ``...Extended`` variants and the internal classes in
# ``cmk.gui.form_specs.unstable`` are covered without importing them (they move
# between releases). The node format is the one the valuespec walker produces,
# describing the value as stored - which is what ``value_raw`` holds.


def _localize(text: object) -> str | None:
    if text is None:
        return None
    localize = getattr(text, "localize", None)
    if localize is None:
        return _text(text)
    from cmk.gui.i18n import _

    return _text(_safe(lambda: localize(_)))


def _class_names(obj: object) -> list[str]:
    return [cls.__name__ for cls in type(obj).__mro__]


def _form_spec_bounds(node: Node, fs: Any) -> None:
    """min/max from a ``NumberInRange`` validator, if the FormSpec has one."""
    for validator in getattr(fs, "custom_validate", None) or ():
        if type(validator).__name__ != "NumberInRange":
            continue
        if (lower := getattr(validator, "range", (None, None))[0]) is not None:
            node["min"] = lower
        if (upper := getattr(validator, "range", (None, None))[1]) is not None:
            node["max"] = upper


def _form_spec_elements(fs: Any) -> Iterable[Any]:
    """A choice FormSpec's elements; the internal variants may compute them."""
    elements = getattr(fs, "elements", None) or ()
    if callable(elements):
        elements = _safe(elements, ()) or ()
    return elements


def _levels_node(fs: Any, child: Callable[[Any], Node]) -> list[dict[str, Any]]:
    """Stored levels: ("no_levels", None) | ("fixed", (warn, crit)) [| ("predictive", {...})]."""
    template = child(fs.form_spec_template)
    choices: list[dict[str, Any]] = [
        {"value": "no_levels", "title": "No levels", "schema": {"type": "fixed", "value": None}},
        {
            "value": "fixed",
            "title": "Fixed levels",
            "schema": {"type": "tuple", "elements": [template, template]},
        },
    ]
    if getattr(fs, "predictive", None) is not None:
        choices.append(
            {
                "value": "predictive",
                "title": "Predictive levels",
                "schema": {"type": "dictionary_unknown"},
            }
        )
    return choices


def describe_form_spec(fs: Any, *, depth: int = 0) -> Node:  # noqa: C901 - one flat dispatch
    names = _class_names(fs)
    node: Node = {
        "type": "unknown",
        "form_spec": names[0],
        "title": _localize(getattr(fs, "title", None)),
        "help": _localize(getattr(fs, "help_text", None)),
    }
    if depth > MAX_DEPTH:
        node["type"] = "truncated"
        return node

    def child(inner: Any) -> Node:
        return describe_form_spec(inner, depth=depth + 1)

    def is_(*candidates: str) -> bool:
        return any(name in names for name in candidates)

    if is_("TransformDataForLegacyFormatOrRecomposeFunction"):
        inner = child(fs.wrapped_form_spec)
        inner["title"] = node["title"] or inner["title"]
        inner["help"] = node["help"] or inner["help"]
        inner["transformed"] = True  # to_disk may store another shape
        return inner
    if is_("LegacyValueSpec"):
        valuespec = getattr(fs, "valuespec", None)
        return node if valuespec is None else describe(valuespec, depth=depth + 1)
    if is_("TimeSpecific"):
        node.update(
            type="timespecific",
            element=child(fs.parameter_form),
            default_key="tp_default_value",
            values_key="tp_values",
        )
    elif is_("Dictionary", "TwoColumnDictionary"):
        node.update(
            type="dictionary",
            elements=[
                {
                    "key": key,
                    "required": bool(getattr(element, "required", False)),
                    "hidden": bool(getattr(element, "render_only", False)),
                    "schema": child(element.parameter_form),
                }
                for key, element in (getattr(fs, "elements", None) or {}).items()
            ],
        )
    elif is_("Tuple"):
        node.update(type="tuple", elements=[child(e) for e in fs.elements])
    elif is_("CascadingSingleChoice", "CascadingSingleChoiceExtended"):
        choices, truncated = _first(_form_spec_elements(fs), MAX_CHOICES)
        node.update(
            type="cascading",
            choices=[
                {
                    "value": _jsonable(e.name),
                    "title": _localize(e.title),
                    "schema": child(e.parameter_form),
                }
                for e in choices
            ],
            truncated=truncated,
        )
    elif is_("SingleChoice", "SingleChoiceExtended", "SingleChoiceEditable", "MultipleChoice"):
        choices, truncated = _first(_form_spec_elements(fs), MAX_CHOICES)
        node.update(
            type="multiple_choice" if is_("MultipleChoice") else "choice",
            choices=[{"value": _jsonable(e.name), "title": _localize(e.title)} for e in choices],
            truncated=truncated,
        )
    elif is_("ServiceState", "HostState"):
        states = (
            [(0, "OK"), (1, "WARN"), (2, "CRIT"), (3, "UNKNOWN")]
            if is_("ServiceState")
            else [(0, "UP"), (1, "DOWN"), (2, "UNREACHABLE")]
        )
        node.update(type="choice", choices=[{"value": v, "title": t} for v, t in states])
    elif is_("FixedValue"):
        node.update(type="fixed", value=_jsonable(fs.value))
    elif is_("SimpleLevels", "Levels"):
        node.update(type="cascading", choices=_levels_node(fs, child), truncated=False)
    elif is_("Percentage"):
        node.update(type="float", unit="percent")
        _form_spec_bounds(node, fs)
    elif is_("TimeSpan"):
        node.update(type="float", unit="seconds")
        _form_spec_bounds(node, fs)
    elif is_("DataSize"):
        node.update(type="integer", unit="bytes")
        _form_spec_bounds(node, fs)
    elif is_("Integer"):
        node["type"] = "integer"
        _form_spec_bounds(node, fs)
    elif is_("Float"):
        node["type"] = "float"
        _form_spec_bounds(node, fs)
    elif is_("BooleanChoice"):
        node["type"] = "boolean"
    elif is_("String", "MultilineText", "RegularExpression", "CommentTextArea"):
        node["type"] = "string"
    elif is_("Password", "PasswordStorePassword"):
        node.update(
            type="password",
            format=(
                "('cmk_postprocessed', 'explicit_password', (<id>, <password>)) or "
                "('cmk_postprocessed', 'stored_password', (<password store id>, ''))"
            ),
            secret=True,
        )
    elif is_("List", "ListOfStrings"):
        template = getattr(fs, "element_template", None) or getattr(fs, "string_spec", None)
        node.update(
            type="list", element=child(template) if template is not None else {"type": "unknown"}
        )
    elif is_("OptionalChoice") and getattr(fs, "parameter_form", None) is not None:
        node.update(type="optional", element=child(fs.parameter_form))
    elif is_("Labels"):
        node["type"] = "labels"
    return node


# --- examples ---------------------------------------------------------------------


def example_from_node(node: Node, *, depth: int = 0) -> Any:
    """A minimal value matching ``node``: required keys only, first choices, zeros.

    For FormSpec rulesets, which have no valuespec ``default_value()``. It shows
    the shape; bounds and validators may still reject the zeros.
    """
    if depth > MAX_DEPTH:
        return None
    kind = node.get("type")

    def sub(inner: Node) -> Any:
        return example_from_node(inner, depth=depth + 1)

    if kind == "dictionary":
        return {e["key"]: sub(e["schema"]) for e in node["elements"] if e["required"]}
    if kind == "tuple":
        return tuple(sub(e) for e in node["elements"])
    if kind in ("list", "multiple_choice", "labels"):
        return {} if kind == "labels" else []
    if kind == "timespecific":
        return sub(node["element"])
    if kind == "optional":
        return None
    if kind == "cascading":
        if not node.get("choices"):
            return None
        first = node["choices"][0]
        return (first["value"], None if first.get("schema") is None else sub(first["schema"]))
    if kind == "choice":
        return node["choices"][0]["value"] if node.get("choices") else None
    if kind == "fixed":
        return node.get("value")
    if kind == "alternative":
        return sub(node["elements"][0]) if node.get("elements") else None
    if kind == "integer":
        return int(node.get("min", 0))
    if kind == "float":
        return float(node.get("min", 0.0))
    if kind == "boolean":
        return False
    if kind == "string":
        return ""
    if kind == "password":
        return ("cmk_postprocessed", "explicit_password", ("<id>", "<password>"))
    return None
