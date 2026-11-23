# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Setup > General > Rule schema explorer."""

from __future__ import annotations

from collections.abc import Sequence

from cmk.gui.i18n import _

try:  # 3.0 moved the icon types out of the GUI package
    from cmk.web.utils.icons import StaticIcon
except ImportError:  # 2.5
    from cmk.gui.type_defs import StaticIcon
from cmk.gui.wato._main_module_topics import MainModuleTopicGeneral
from cmk.gui.watolib.main_menu import ABCMainModule, MainModuleTopic
from cmk.shared_typing.icon import IconNames


class MainModuleRuleSchemaExplorer(ABCMainModule):
    @property
    def topic(self) -> MainModuleTopic:
        return MainModuleTopicGeneral

    @property
    def mode_or_url(self) -> str:
        return "rule_schema_explorer"  # == ModeRuleSchemaExplorer.name()

    @property
    def title(self) -> str:
        return _("Rule schema explorer")

    @property
    def icon(self) -> StaticIcon:
        return StaticIcon(IconNames.rulesets)

    @property
    def permission(self) -> None | str:
        return "rulesets"

    @property
    def description(self) -> str:
        return _("Browse all rulesets and the value schema the REST API expects")

    @property
    def sort_index(self) -> int:
        return 90

    @property
    def is_show_more(self) -> bool:
        return True

    @classmethod
    def main_menu_search_terms(cls) -> Sequence[str]:
        return ["schema", "rest", "api", "value_raw", "ruleset"]
