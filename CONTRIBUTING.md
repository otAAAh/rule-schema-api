<!-- SPDX-License-Identifier: GPL-2.0-only -->
# Contributing

Thanks for taking an interest in **rule-schema-api**! This is a small,
single-maintainer Checkmk extension, so contributions of any size — a bug
report, a doc fix, a schema the walkers describe wrongly, a new feature — are
genuinely welcome.

## Ways to contribute

- **Ask a question or share an idea** →
  [Discussions](https://github.com/otAAAh/rule-schema-api/discussions).
- **Report a bug** → [open an issue](https://github.com/otAAAh/rule-schema-api/issues).
  Include your Checkmk version and edition, the package version, the ruleset
  name and the (redacted) request and response.
- **Report a security problem** → **don't** open a public issue; follow
  [`SECURITY.md`](SECURITY.md) and use GitHub's private advisory flow.
- **Send a change** → open a pull request (see below).

## Development setup

The code imports Checkmk's GUI, which only exists in an installed Checkmk
version. What needs what:

- **Format, lint, build, unit tests** — no Checkmk needed:

  ```sh
  pip install -r requirements-dev.txt
  make lint test-unit mkp
  ```

- **Type check and site tests** — need an installed Checkmk version (any
  `/omd/versions/*`; no site and no site user needed). The Makefile picks the
  newest one; set `CMK_VERSION_DIR` to choose:

  ```sh
  make typecheck test-site
  CMK_VERSION_DIR=/omd/versions/<version> make test-site
  ```

  `make typecheck` installs the pinned mypy for that version's Python into
  `.cmksrc/` and checks against its `cmk` sources. The site tests load the
  whole GUI into a throwaway site directory and walk every ruleset.

  CI runs the site tests inside the official Checkmk container for every
  release line with a public image (2.5 and 3.0), so you don't need both locally.

- **Against a running site** with the package installed:

  ```sh
  python3 tests/smoke_live.py http://localhost/mysite --password ... --language de --all
  ```

## Before you open a PR

Run the same checks CI runs. All of them should be green:

```sh
make lint        # ruff format --check + ruff check (Checkmk's rules)
make typecheck   # mypy (Checkmk's settings)
make test        # unit + site tests
```

## Code style

- Lint, format and type settings are **Checkmk's own** (see `pyproject.toml`),
  with the Python target of the oldest supported release (2.5 = 3.13).
- No `Any`: schema nodes are typed JSON (`_util.Json`), inputs are `object`
  narrowed with `isinstance`.
- Checkmk's GUI internals are unversioned. Import them inside functions, read
  private attributes through one helper, and keep 2.5/3.0 differences in small,
  commented branches.

## Commit messages

The changelog is generated from commit subjects (`scripts/gen_changelog.py`),
so write them for a reader of the release notes:

- one line saying what changed, from the user's point of view;
- a Conventional-Commit prefix sorts it into a section: `feat:` → Features,
  `fix:` → Fixes, anything else → Other (`docs:`, `ci:`, `refactor:`, ...);
- leave the second line empty, then explain *why* in the body.

## Releases

Bump `version` in `pyproject.toml`, add an `UPGRADING.md` section if clients or
admins must do something, run `make changelog`, commit, then push an annotated
`vX.Y.Z` tag. The release workflow builds the MKP, attests its provenance and
publishes the GitHub Release with the changelog section as notes.
