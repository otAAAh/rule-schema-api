<!-- SPDX-License-Identifier: GPL-2.0-only -->
# Upgrade notes

What a site administrator or API client needs to know *before* upgrading —
renamed packages, changed endpoints or fields.

`CHANGELOG.md` is generated from the git history, so it can only say what
changed in the code. This file is hand-written and says what that means for a
running site. Only versions that need a note appear here; a version missing from
this list needs none.

`scripts/gen_changelog.py --version X.Y.Z` appends the matching section to the
GitHub Release body, so these notes travel with the release people actually read.
