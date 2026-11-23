# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Rule schema API: REST endpoints listing every ruleset and its value schema.

Installed to the site's ``local/lib/python3`` (on ``sys.path`` in every site
process). The GUI plugin ``cmk/gui/plugins/wato/rule_schema_api.py`` imports
this package and calls ``register()`` - the only file in the scanned plugin
namespace.

Modules:
    endpoints   the two REST endpoints and their response schemas
    catalog     the ruleset registry, display-name languages, kinds
    valuespec   schema from a ValueSpec
    form_spec   schema from a FormSpec (where Setup has no valuespec)
    example     an example value_raw from a schema
"""


def register() -> None:
    """Add the endpoints to the REST API (imports Checkmk, so only on call)."""
    from .endpoints import register as register_endpoints

    register_endpoints()


__all__ = ["register"]
