# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""REST API endpoints, added to the site's own API (``/api/1.0``).

    GET /domain-types/rule_schema/collections/all[?include_deprecated=true]
    GET /objects/rule_schema/{ruleset_name}

They live in the REST API's endpoint registry next to the built-in ones, so
they get the same authentication (automation user, session cookie), the same
permission check, and a "Rule schemas" section in the API documentation.

How an extension package gets there: on startup the GUI registers the built-in
endpoints, then loads the local GUI plugins (this package); the REST app builds
its routes lazily from the registry on the first request. Same order on 2.5 and
3.0. The legacy ``Endpoint`` decorator used here is internal API but exists on
both; the 2.5/3.0 differences are bridged in ``register``.

The response is dumped through the marshmallow ``response_schema`` - a field
not declared there is silently dropped, so every collection field is spelled
out. The value schema tree is recursive and free-form, hence ``fields.Dict``.
"""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus

from cmk import fields
from cmk.gui.fields.base import BaseSchema
from cmk.gui.http import Response
from cmk.gui.logged_in import user
from cmk.gui.openapi.restful_objects import Endpoint
from cmk.gui.openapi.restful_objects.endpoint_family import EndpointFamily
from cmk.gui.openapi.utils import problem, serve_json

try:  # 3.0
    from cmk.web.utils import permission_verification as permissions
except ImportError:  # 2.5
    # 2.5 location. Type-checked against 3.0, where it moved to cmk.web.
    from cmk.gui.utils import permission_verification as permissions  # type: ignore[attr-defined, no-redef, unused-ignore]

from .catalog import (
    KNOWN_KINDS,
    list_rulesets,
    parameter_names,
    ruleset_schema,
    UnknownRuleset,
    user_language,
)

FAMILY_NAME = "Rule schemas"

RULE_SCHEMA_FAMILY = EndpointFamily(
    name=FAMILY_NAME,
    description=(
        "Every Setup ruleset and the shape of its rule value.\n\n"
        "The rules endpoints take a rule's value as `value_raw`, a Python literal "
        "string, and nothing in the API describes what it may contain. These "
        "endpoints list all rulesets and describe the value of each one: the "
        "structure, keys, types, choices and bounds, plus an example `value_raw` "
        "to start from.\n\n"
        "Provided by the *Rule schema API* extension package (rule_schema_api)."
    ),
    doc_group="Setup",
)

PERMISSIONS = permissions.AllPerm([permissions.Perm("wato.use"), permissions.Perm("wato.rulesets")])

_KIND_HELP = (
    "What the ruleset is for, from its name prefix: "
    + ", ".join(f"`{k}`" for k in KNOWN_KINDS)
    + ". `general` are rulesets without a prefix (groups, tags, ...). A prefix not "
    "known to this package is reported as the prefix itself."
)

_NAME_HELP = (
    "Only present when the requesting user's language is not English: the same name, translated."
)


class RuleSchemaEntry(BaseSchema):
    ruleset_name = fields.String(
        required=True,
        description="The ruleset's name - what the rules endpoints call `ruleset`.",
        example="checkgroup_parameters:filesystem",
    )
    kind = fields.String(
        required=True,
        description=_KIND_HELP,
        example="service_parameters",
    )
    display_name_en = fields.String(
        required=True,
        description="The ruleset's title in English, as shown in Setup.",
        example="Filesystems (used space and growth)",
    )
    display_name = fields.String(
        description=f"The ruleset's title in the user's language. {_NAME_HELP}",
        example="Dateisysteme (belegter Platz und Wachstum)",
    )
    group = fields.String(
        required=True,
        description="The Setup group the ruleset is listed in.",
        example="checkparams/storage",
    )
    group_display_name_en = fields.String(required=True, description="The group's English title.")
    group_display_name = fields.String(description=f"The group's title. {_NAME_HELP}")
    match_type = fields.String(
        required=True,
        description="How matching rules combine: first, all, list, dict or varies.",
        example="first",
    )
    item_type = fields.String(
        allow_none=True,
        description="'service' or 'item' if rules match on a service/item, else null.",
    )
    is_deprecated = fields.Boolean(required=True, description="Whether the ruleset is deprecated.")
    is_form_spec = fields.Boolean(
        required=True, description="Whether the ruleset is defined with the FormSpec API."
    )


class RuleSchemaCollection(BaseSchema):
    domainType = fields.String(description="The domain type of the objects.", example="rule_schema")
    value = fields.List(fields.Nested(RuleSchemaEntry), description="All rulesets.")


class RuleSchemaObject(BaseSchema):
    ruleset_name = fields.String(required=True, description="The ruleset's name.")
    kind = fields.String(
        required=True,
        description=_KIND_HELP,
        example="service_parameters",
    )
    display_name_en = fields.String(required=True, description="The ruleset's English title.")
    display_name = fields.String(description=_NAME_HELP)
    help = fields.String(allow_none=True, description="The ruleset's help text, plain text.")
    match_type = fields.String(required=True, description="How matching rules combine.")
    item_type = fields.String(allow_none=True, description="'service', 'item' or null.")
    item_name = fields.String(allow_none=True, description="What the item is called in Setup.")
    item_schema = fields.Dict(
        allow_none=True, description="Schema of the rule condition's item, for item rulesets."
    )
    schema_source = fields.String(
        required=True,
        description=(
            "'valuespec' or 'form_spec': where the schema was read from. FormSpec "
            "rulesets Checkmk cannot convert to a valuespec are read from the "
            "FormSpec directly."
        ),
        example="valuespec",
    )
    schema = fields.Dict(
        required=True,
        description=(
            "The value's shape as a node tree. Every node has `type` (dictionary, "
            "tuple, list, cascading, alternative, optional, choice, multiple_choice, "
            "fixed, timespecific, string, password, integer, float, boolean, labels or "
            "unknown), `title`, "
            "`help` and `valuespec`, plus `elements`/`element`/`choices`/`min`/`max` "
            "where they apply."
        ),
    )
    example_value_raw = fields.String(
        allow_none=True,
        description="A valid `value_raw` to start from: the ruleset's default value.",
        example="{'levels': (80.0, 90.0)}",
    )


LIST_QUERY = {
    "kind": fields.List(
        fields.String(),
        load_default=[],
        required=False,
        description=(
            "Only list rulesets of these kinds; repeat the parameter for several "
            "(`?kind=service_parameters&kind=discovery`). Omitted: all kinds. " + _KIND_HELP
        ),
        example=["service_parameters", "discovery"],
    ),
    "include_deprecated": fields.Boolean(
        load_default=False,
        required=False,
        description="Also list deprecated rulesets.",
        example=False,
    ),
}

RULESET_NAME = {
    "ruleset_name": fields.String(
        required=True,
        description="The ruleset's name, as listed in the collection.",
        example="checkgroup_parameters:filesystem",
    )
}


@Endpoint(
    "/domain-types/rule_schema/collections/all",
    ".../collection",
    method="get",
    query_params=[LIST_QUERY],
    response_schema=RuleSchemaCollection,
    permissions_required=PERMISSIONS,
    family_name=FAMILY_NAME,
)
def list_rule_schemas(params: Mapping[str, object]) -> Response:
    """List all rulesets"""
    user.need_permission("wato.use")
    user.need_permission("wato.rulesets")
    return serve_json(
        {
            "domainType": "rule_schema",
            "value": list_rulesets(
                include_deprecated=bool(params.get("include_deprecated")),
                lang=user_language(),
                kinds=_kinds(params.get("kind")),
            ),
        }
    )


@Endpoint(
    "/objects/rule_schema/{ruleset_name}",
    "cmk/show",
    method="get",
    path_params=[RULESET_NAME],
    response_schema=RuleSchemaObject,
    permissions_required=PERMISSIONS,
    family_name=FAMILY_NAME,
)
def show_rule_schema(params: Mapping[str, object]) -> Response:
    """Show the value schema of a ruleset"""
    user.need_permission("wato.use")
    user.need_permission("wato.rulesets")
    name = str(params["ruleset_name"])
    try:
        return serve_json(ruleset_schema(name, lang=user_language()))
    except UnknownRuleset:
        return problem(
            status=HTTPStatus.NOT_FOUND,
            title="Unknown ruleset.",
            detail=f"The ruleset of name {name!r} is not known.",
        )


def _kinds(value: object) -> frozenset[str] | None:
    """The ``kind`` query values (a list after parsing), or None for "all kinds"."""
    if not isinstance(value, list) or not value:
        return None
    return frozenset(str(kind) for kind in value)


def _register(register: object, obj: object) -> None:
    """2.5's registries take a mandatory ``ignore_duplicates``; 3.0's don't."""
    if not callable(register):
        raise TypeError(f"not a registry method: {register!r}")
    if "ignore_duplicates" in parameter_names(register):
        register(obj, ignore_duplicates=True)
    else:
        register(obj)


def register() -> None:
    from cmk.gui.openapi import endpoint_family_registry, endpoint_registry

    if endpoint_family_registry.get(FAMILY_NAME) is None:
        _register(endpoint_family_registry.register, RULE_SCHEMA_FAMILY)
    _register(endpoint_registry.register, list_rule_schemas)
    _register(endpoint_registry.register, show_rule_schema)
