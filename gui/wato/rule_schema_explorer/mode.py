# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""The explorer as a Setup mode: ``wato.py?mode=rule_schema_explorer``.

A WatoMode gets the native Setup chrome (breadcrumb, page menu) for free. The
page itself is a static shell; ``rule_schema_explorer/app.js`` (shipped in the
``web`` part) fetches the two AJAX endpoints and renders the browser. No build
step and no dependency on cmk-frontend-vue internals.
"""

from __future__ import annotations

from cmk.gui.htmllib.html import html
from cmk.gui.http import request
from cmk.gui.i18n import _
from cmk.gui.watolib.mode import WatoMode

_ASSETS = "rule_schema_explorer"


class ModeRuleSchemaExplorer(WatoMode):
    @classmethod
    def name(cls) -> str:
        return "rule_schema_explorer"

    @staticmethod
    def static_permissions() -> list[str]:
        return ["rulesets"]

    def title(self) -> str:
        return _("Rule schema explorer")

    def page(self, config: object) -> None:
        html.stylesheet(f"{_ASSETS}/app.css")
        # ?ruleset=<name> deep-links straight to one ruleset's schema.
        preselect = request.get_ascii_input("ruleset")
        html.open_div(id_="rse-app", data_preselect=preselect)
        html.close_div()
        html.javascript_file(f"{_ASSETS}/app.js")
