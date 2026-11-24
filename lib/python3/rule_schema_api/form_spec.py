# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Describe a rule value from its FormSpec, where Setup has no valuespec for it.

On 3.0 some FormSpec rulesets can no longer be turned into a valuespec
(``rulespec.valuespec`` raises NotImplementedError), so their schema is read
from the FormSpec itself. FormSpecs are dataclasses; dispatch is by class name
along the MRO, so the ``...Extended`` variants and the internal classes in
``cmk.gui.form_specs.unstable`` are covered without importing them (they move
between releases). The node format is the valuespec walker's, describing the
value as stored - which is what ``value_raw`` holds.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from ._util import first, iterable, Json, jsonable, MAX_CHOICES, MAX_DEPTH, Node, safe, text
from .valuespec import describe_valuespec


def _field(fs: object, name: str) -> object:
    return getattr(fs, name, None)


def _localize(value: object) -> str | None:
    """A ``Title``/``Help``/``Label`` in the active GUI language, or plain text."""
    if value is None:
        return None
    localize = getattr(value, "localize", None)
    if not callable(localize):
        return text(value)
    from cmk.gui.i18n import _

    return text(safe(lambda: localize(_), None))


def _class_names(obj: object) -> list[str]:
    return [cls.__name__ for cls in type(obj).__mro__]


def _form_spec_constraints(node: Node, fs: object) -> None:
    """What the FormSpec's validators demand, as schema keys.

    Bounds go to min/max (numbers) or min_length/max_length (text) or
    min_items/max_items (lists); URL and e-mail validators set ``format``.
    """
    kind = node.get("type")
    for validator in iterable(_field(fs, "custom_validate")):
        name = type(validator).__name__
        if name in ("NumberInRange", "LengthInRange"):
            limits = getattr(validator, "range", None)
            if not (isinstance(limits, tuple) and len(limits) == 2):
                continue
            if name == "NumberInRange":
                keys = ("min", "max")
            elif kind in ("list", "multiple_choice"):
                keys = ("min_items", "max_items")
            else:
                keys = ("min_length", "max_length")
            for key, limit in zip(keys, limits, strict=True):
                if isinstance(limit, int | float) and not isinstance(limit, bool):
                    node[key] = limit
        elif name == "Url":
            node["format"] = "url"
            protocols: list[Json] = [
                str(getattr(p, "value", p)) for p in iterable(_field(validator, "protocols"))
            ]
            if protocols:
                node["protocols"] = protocols
        elif name == "EmailAddress":
            node["format"] = "email"
        elif name == "MatchRegex":
            regex = _field(validator, "regex")
            node["pattern"] = str(getattr(regex, "pattern", regex))
        elif name == "NetworkPort":
            node["min"], node["max"] = 0, 65535


def _form_spec_elements(fs: object) -> Iterable[object]:
    """A choice FormSpec's elements; the internal variants may compute them."""
    elements = _field(fs, "elements")
    if callable(elements):
        elements = safe(elements, ())
    return iterable(elements)


def _levels_choices(fs: object, child: Callable[[object], Node]) -> list[Json]:
    """Stored levels: ("no_levels", None) | ("fixed", (warn, crit)) [| ("predictive", {...})]."""
    template = child(_field(fs, "form_spec_template"))
    choices: list[Json] = [
        {"value": "no_levels", "title": "No levels", "schema": {"type": "fixed", "value": None}},
        {
            "value": "fixed",
            "title": "Fixed levels",
            "schema": {"type": "tuple", "elements": [template, template]},
        },
    ]
    if _field(fs, "predictive") is not None:
        choices.append(
            {
                "value": "predictive",
                "title": "Predictive levels",
                "schema": {"type": "dictionary_unknown"},
            }
        )
    return choices


def describe_form_spec(fs: object, *, depth: int = 0) -> Node:
    names = _class_names(fs)
    node: Node = {
        "type": "unknown",
        "form_spec": names[0],
        "title": _localize(_field(fs, "title")),
        "help": _localize(_field(fs, "help_text")),
    }
    if depth > MAX_DEPTH:
        node["type"] = "truncated"
        return node

    def child(inner: object) -> Node:
        return describe_form_spec(inner, depth=depth + 1)

    def is_(*candidates: str) -> bool:
        return any(name in names for name in candidates)

    if is_("TransformDataForLegacyFormatOrRecomposeFunction"):
        inner = child(_field(fs, "wrapped_form_spec"))
        inner["title"] = node["title"] or inner["title"]
        inner["help"] = node["help"] or inner["help"]
        inner["transformed"] = True  # to_disk may store another shape
        return inner
    if is_("LegacyValueSpec"):
        valuespec = _field(fs, "valuespec")
        return node if valuespec is None else describe_valuespec(valuespec, depth=depth + 1)
    if is_("TimeSpecific"):
        node.update(
            type="timespecific",
            element=child(_field(fs, "parameter_form")),
            default_key="tp_default_value",
            values_key="tp_values",
        )
    elif is_("Dictionary", "TwoColumnDictionary"):
        raw = _field(fs, "elements")
        elements: list[Json] = [
            {
                "key": str(key),
                "required": bool(getattr(element, "required", False)),
                "hidden": bool(getattr(element, "render_only", False)),
                "schema": child(_field(element, "parameter_form")),
            }
            for key, element in (raw.items() if isinstance(raw, Mapping) else ())
        ]
        node.update(type="dictionary", elements=elements)
    elif is_("Tuple"):
        node.update(type="tuple", elements=[child(e) for e in iterable(_field(fs, "elements"))])
    elif is_("CascadingSingleChoice", "CascadingSingleChoiceExtended"):
        shown, truncated = first(_form_spec_elements(fs), MAX_CHOICES)
        cascading: list[Json] = [
            {
                "value": jsonable(_field(e, "name")),
                "title": _localize(_field(e, "title")),
                "schema": child(_field(e, "parameter_form")),
            }
            for e in shown
        ]
        node.update(
            type="cascading", choices=cascading, truncated=truncated, selection_required=True
        )
    elif is_("SingleChoice", "SingleChoiceExtended", "SingleChoiceEditable", "MultipleChoice"):
        shown, truncated = first(_form_spec_elements(fs), MAX_CHOICES)
        choices: list[Json] = [
            {"value": jsonable(_field(e, "name")), "title": _localize(_field(e, "title"))}
            for e in shown
        ]
        node.update(
            type="multiple_choice" if is_("MultipleChoice") else "choice",
            choices=choices,
            truncated=truncated,
        )
        if not is_("MultipleChoice"):
            node["selection_required"] = True
    elif is_("ServiceState", "HostState"):
        states = (
            [(0, "OK"), (1, "WARN"), (2, "CRIT"), (3, "UNKNOWN")]
            if is_("ServiceState")
            else [(0, "UP"), (1, "DOWN"), (2, "UNREACHABLE")]
        )
        state_choices: list[Json] = [{"value": value, "title": title} for value, title in states]
        node.update(type="choice", choices=state_choices)
    elif is_("FixedValue"):
        node.update(type="fixed", value=jsonable(_field(fs, "value")))
    elif is_("SimpleLevels", "Levels"):
        node.update(type="cascading", choices=_levels_choices(fs, child), truncated=False)
    elif is_("Percentage"):
        node.update(type="float", unit="percent")
    elif is_("TimeSpan"):
        node.update(type="float", unit="seconds")
    elif is_("DataSize"):
        node.update(type="integer", unit="bytes")
    elif is_("Integer"):
        node["type"] = "integer"
    elif is_("Float"):
        node["type"] = "float"
    elif is_("BooleanChoice"):
        node["type"] = "boolean"
    elif is_(
        "String",
        "MultilineText",
        "RegularExpression",
        "CommentTextArea",
        "Metric",
        "MonitoredHost",
        "MonitoredService",
    ):
        node["type"] = "string"
    elif is_("Proxy", "InternalProxy"):
        node.update(
            type="proxy",
            format=(
                "('cmk_postprocessed', 'environment_proxy' | 'no_proxy', '') or "
                "('cmk_postprocessed', 'stored_proxy', <proxy id>) or "
                "('cmk_postprocessed', 'explicit_proxy', <proxy URL>)"
            ),
        )
    elif is_("TimePeriod"):
        node.update(
            type="time_period",
            format="('cmk_postprocessed', 'stored_time_period', <time period name>)",
        )
    elif is_("OAuth2Connection"):
        node.update(
            type="oauth2_connection",
            format="('cmk_postprocessed', 'oauth2_connection', <connection id>)",
        )
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
        template = _field(fs, "element_template") or _field(fs, "string_spec")
        node.update(
            type="list", element=child(template) if template is not None else {"type": "unknown"}
        )
    elif is_("OptionalChoice") and _field(fs, "parameter_form") is not None:
        node.update(type="optional", element=child(_field(fs, "parameter_form")))
    elif is_("Labels"):
        node["type"] = "labels"
    _form_spec_constraints(node, fs)
    return node
