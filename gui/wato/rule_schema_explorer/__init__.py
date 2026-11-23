# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Rule schema explorer GUI plugin: two REST API endpoints, a Setup page, a menu entry.

The GUI imports this package when it walks its plugin namespace on startup,
after the built-in REST endpoints are registered and before the REST app builds
its routes (see ``api``).
"""

from cmk.gui.watolib.main_menu import main_module_registry
from cmk.gui.watolib.mode import mode_registry

from . import api
from .menu import MainModuleRuleSchemaExplorer
from .mode import ModeRuleSchemaExplorer

api.register()
mode_registry.register(ModeRuleSchemaExplorer)
main_module_registry.register(MainModuleRuleSchemaExplorer)
