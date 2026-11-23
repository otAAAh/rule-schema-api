# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Load the rule schema REST endpoints into the GUI.

Checkmk has no plug-in namespace for REST endpoints, so this file sits in the
Setup ("wato") one, which the GUI imports on startup after registering its own
endpoints. The code lives in ``local/lib/python3/rule_schema_api``.
"""

import rule_schema_api

rule_schema_api.register()
