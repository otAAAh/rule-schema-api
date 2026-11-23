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

## [0.3.0]

### The package is renamed to `rule_schema_api`

Up to 0.2.0 the package was called `rule_schema_explorer`. Both register the
same REST endpoints, so **remove the old package before installing this one**:

```sh
mkp disable rule_schema_explorer <old version>
mkp remove rule_schema_explorer <old version>
mkp add rule_schema_api-0.3.0.mkp
mkp enable rule_schema_api 0.3.0
```

The endpoints and their responses are unchanged.

## [0.2.0]

### The Setup page is gone

The package is API only: the *Rule schema explorer* page under Setup › General
was removed. Every entry now has a `kind` field, and the collection takes a
repeatable `?kind=` filter.
