# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Rule schema explorer: two REST API endpoints, nothing else.

The GUI imports this package when it walks its plugin namespace on startup,
after the built-in REST endpoints are registered and before the REST app builds
its routes (see ``api``).
"""

from . import api

api.register()
