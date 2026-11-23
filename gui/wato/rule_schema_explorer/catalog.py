# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Every Setup ruleset, and the schema of one ruleset's rule value.

The site's REST API already has ``GET /domain-types/ruleset/collections/all``,
but it reports a single title, only for rulesets with rules loaded, and no
value schema. This reads the rulespec *registry* (what exists), not the rule
files (what is configured): cheaper, and it covers rulesets nobody used yet.

Names: every entry carries the ruleset name and its English display name. The
display name in the requesting user's language is added only when that language
is not English - so a client can always match on the stable English title and
still show the user's own.

Internal, unversioned GUI APIs: imported on use.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from .schema import (
    Node,
    _text,
    describe,
    describe_form_spec,
    example_from_node,
    example_value_raw,
    python_literal,
)

ENGLISH = "en"


def parameter_names(fn: Callable[..., object]) -> tuple[str, ...]:
    """A function's parameter names, without evaluating its annotations.

    ``inspect.signature`` evaluates them, and Checkmk annotates with names it
    only imports under ``TYPE_CHECKING`` (a NameError on Python 3.14+).
    """
    code = getattr(fn, "__func__", fn).__code__
    return code.co_varnames[: code.co_argcount + code.co_kwonlyargcount]


def _localize(lang: str) -> None:
    """Switch the request's GUI language. 3.0 added a second argument."""
    from cmk.gui import i18n

    if "user_localizations" in parameter_names(i18n.localize):
        from cmk.gui.config import active_config

        i18n.localize(lang, active_config.user_localizations)
    else:  # 2.5
        i18n.localize(lang)


def user_language() -> str:
    """The logged-in (or automation) user's GUI language; English by default."""
    from cmk.gui.logged_in import user

    try:
        return user.language or ENGLISH
    except Exception:  # noqa: BLE001 - no user context (tests, scripts)
        return ENGLISH


@contextmanager
def language(lang: str) -> Iterator[None]:
    """Render titles in ``lang`` for the duration of the block.

    REST requests start unlocalized (built-in endpoints call ``localize``
    themselves), so leaving the block switches back to English, not to
    whatever was active before.
    """
    _localize(lang)
    try:
        yield
    finally:
        _localize(ENGLISH)


def _visible(name: str) -> bool:
    """Setup's own filter (only hides rulesets in the cloud edition)."""
    try:
        from cmk.gui.watolib.rulesets import visible_ruleset
    except ImportError:
        return True
    return visible_ruleset(name)


def _safe_str(fn: Callable[[], object]) -> str | None:
    try:
        value = fn()
    except Exception:  # noqa: BLE001 - an MKP's title() may raise
        return None
    return None if value is None else str(value)


def _group_title(group_name: str) -> str:
    from cmk.gui.watolib.rulespecs import get_rulegroup

    return _safe_str(lambda: get_rulegroup(group_name).title) or group_name


def _rulespecs(include_deprecated: bool) -> list[Any]:
    from cmk.gui.watolib.rulespecs import rulespec_registry

    return [
        rulespec_registry[name]
        for name in rulespec_registry.keys()  # noqa: SIM118 - a Registry, not a dict
        if (include_deprecated or not rulespec_registry[name].is_deprecated) and _visible(name)
    ]


def _names(rulespec: Any) -> dict[str, str]:
    """Title and group title in the currently active language."""
    return {
        "title": _safe_str(lambda: rulespec.title) or rulespec.name,
        "group_title": _group_title(rulespec.group_name),
    }


def _with_display_names(
    rulespecs: list[Any], lang: str
) -> list[tuple[Any, dict[str, str], dict[str, str] | None]]:
    """Each rulespec with its English names, and its names in ``lang`` unless English."""
    with language(ENGLISH):
        english = [_names(r) for r in rulespecs]
    if lang == ENGLISH:
        return [(r, en, None) for r, en in zip(rulespecs, english, strict=True)]
    with language(lang):
        local = [_names(r) for r in rulespecs]
    return list(zip(rulespecs, english, local, strict=True))


def list_rulesets(*, include_deprecated: bool = False, lang: str = ENGLISH) -> list[dict[str, Any]]:
    """All rulesets the user can see in Setup, sorted by group then English title."""
    result = []
    for rulespec, en, local in _with_display_names(_rulespecs(include_deprecated), lang):
        entry: dict[str, Any] = {
            "ruleset_name": rulespec.name,
            "display_name_en": en["title"],
            "group": rulespec.group_name,
            "group_display_name_en": en["group_title"],
            "match_type": rulespec.match_type,
            "item_type": rulespec.item_type,
            "is_deprecated": rulespec.is_deprecated,
            "is_form_spec": bool(getattr(rulespec, "has_form_spec", False)),
        }
        if local is not None:
            entry["display_name"] = local["title"]
            entry["group_display_name"] = local["group_title"]
        result.append(entry)
    result.sort(key=lambda e: (e["group"], e["display_name_en"].lower()))
    return result


class UnknownRuleset(KeyError):
    pass


def ruleset_schema(name: str, *, lang: str = ENGLISH) -> dict[str, Any]:
    """One ruleset's value schema, plus an example ``value_raw``.

    The schema's titles and help texts are in ``lang`` (they are what a person
    reads); the display names follow the same rule as the collection.
    """
    from cmk.gui.watolib.rulespecs import rulespec_registry

    if name not in rulespec_registry or not _visible(name):
        raise UnknownRuleset(name)
    rulespec = rulespec_registry[name]
    ((_, en, local),) = _with_display_names([rulespec], lang)

    with language(lang):
        schema, example, source = _value_schema(rulespec)
        item_spec = _safe_item_spec(rulespec)
        result: dict[str, Any] = {
            "ruleset_name": name,
            "display_name_en": en["title"],
            "help": _text(_safe_str(lambda: rulespec.help)),
            "match_type": rulespec.match_type,
            "item_type": rulespec.item_type,
            "item_name": _safe_str(lambda: rulespec.item_name),
            "item_schema": None if item_spec is None else describe(item_spec),
            "schema_source": source,
            "schema": schema,
            "example_value_raw": example,
        }
    if local is not None:
        result["display_name"] = local["title"]
    return result


def _value_schema(rulespec: Any) -> tuple[Node, str | None, str]:
    """(schema, example value_raw, source) - from the valuespec where Setup can
    still build one, else from the FormSpec (3.0 cannot convert every FormSpec)."""
    try:
        valuespec = rulespec.valuespec
    except NotImplementedError:
        if not getattr(rulespec, "has_form_spec", False):
            raise
        schema = describe_form_spec(rulespec.form_spec)
        return schema, python_literal(example_from_node(schema)), "form_spec"
    return describe(valuespec), example_value_raw(valuespec), "valuespec"


def _safe_item_spec(rulespec: Any) -> Any:
    if rulespec.item_type != "item":
        return None
    try:
        return rulespec.item_spec
    except NotImplementedError:
        return None


__all__ = ["Node", "UnknownRuleset", "list_rulesets", "ruleset_schema", "user_language"]
