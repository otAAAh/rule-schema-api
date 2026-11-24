<!-- SPDX-License-Identifier: GPL-2.0-only -->
# rule-schema-api

[![CI](https://github.com/otAAAh/rule-schema-api/actions/workflows/ci.yml/badge.svg)](https://github.com/otAAAh/rule-schema-api/actions/workflows/ci.yml)
[![CodeQL](https://github.com/otAAAh/rule-schema-api/actions/workflows/codeql.yml/badge.svg)](https://github.com/otAAAh/rule-schema-api/actions/workflows/codeql.yml)
[![Checkmk 2.5+](https://img.shields.io/badge/Checkmk-2.5%2B-15d1a0?logo=checkmk&logoColor=white)](#build--install)
[![License: GPL v2](https://img.shields.io/badge/License-GPLv2-blue.svg)](LICENSE)

A Checkmk extension package (MKP, **Checkmk 2.5+**) that adds two endpoints to
the site's own REST API. API only - no GUI.

The rules endpoints take a rule's value as `value_raw`, a Python literal
string, but nothing in the API says what that value may contain. This package
lists every ruleset and describes the shape of its value.

## Endpoints

Both live under `/<site>/check_mk/api/1.0`, use the normal REST API
authentication, and need the `wato.use` + `wato.rulesets` permissions.

They do **not** show up in the site's API documentation (Swagger/ReDoc): that
is a spec file generated when Checkmk is built, not from the endpoints
registered at runtime. This README is their documentation.

| Method | Path | Returns |
|---|---|---|
| GET | `/domain-types/rule_schema/collections/all[?kind=...][&include_deprecated=true]` | every ruleset, optionally filtered by kind |
| GET | `/objects/rule_schema/{ruleset_name}` | one ruleset's value schema |
| POST | `/objects/rule_schema/{ruleset_name}/actions/validate/invoke` | check a `value_raw` without creating a rule |

Each collection entry has `ruleset_name`, `kind`, `display_name_en` (English title),
`group`, `group_display_name_en`, `match_type`, `item_type`, `is_deprecated`
and `is_form_spec`. When the requesting user's language is **not** English,
`display_name` and `group_display_name` (translated) are added.

The object adds the item schema, `schema` (a node tree: `type`, `title`,
`help`, plus `elements` / `element` / `choices` / `min` / `max` / `unit` ...
where they apply), `schema_source` (`valuespec` or `form_spec`) and an
`example_value_raw` to start from.

`example_value_raw` is checked with the rules API's own value check before it
is returned; `example_valid` says whether `POST /domain-types/rule/collections/all`
accepts it unchanged. Where Checkmk's default is rejected (an empty user name,
URL, ...), the example is built from the schema with placeholders instead. If
neither passes, `example_problems` lists what to fill in - typically
credentials, or objects that must exist first (host groups, contact groups).

The validate endpoint runs that same check on any value and returns
`{"valid": ..., "problems": [{"title": ..., "detail": ...}]}`. Nothing is
created or changed. It checks the value only - not the folder, conditions or
permissions of a real rule.

The schema shows the constraints the check enforces where it can read them:
`min_length`/`max_length`, `min_items`/`max_items`, `format` (`url`,
`email`), `pattern`, and `selection_required`. Validators that are plain
functions (e.g. "a valid API key") cannot be shown; the validate endpoint
still checks them.

```sh
curl -u cmkadmin:$PASSWORD \
  "http://localhost/mysite/check_mk/api/1.0/objects/rule_schema/checkgroup_parameters:filesystem"
```

## Kinds

`kind` comes from the ruleset name's prefix; filter with a repeatable
`?kind=` (`?kind=service_parameters&kind=discovery`):

| kind | prefix |
|---|---|
| `service_parameters` | `checkgroup_parameters:` |
| `enforced_services` | `static_checks:` |
| `discovery` | `discovery_parameters:` |
| `agent_config` | `agent_config:` |
| `special_agents` | `special_agents:` |
| `active_checks` | `active_checks:` |
| `service_monitoring` | `extra_service_conf:` |
| `host_monitoring` | `extra_host_conf:` |
| `notification_parameters` | `notification_parameters:` |
| `inventory` | `inv_parameters:` |
| `general` | no prefix (groups, tags, ...) |

On 2.5, discovery rulesets have no `discovery_parameters:` prefix (it came with
3.0); a ruleset listed in the Setup group `checkparams/discovery` is `discovery`
on both. An unknown prefix is reported as the prefix itself.

## How it works

- The ruleset list is Setup's in-memory `rulespec_registry`, not the rule files.
- The schema is read from the ruleset's valuespec, which is the value space
  `value_raw` uses. On 3.0, FormSpec rulesets Checkmk cannot convert to a
  valuespec are read from the FormSpec directly.
- An extension can add REST endpoints because the GUI registers the built-in
  endpoints, then loads local GUI plugins, and the REST app builds its routes
  lazily from the registry on the first request.

These are internal, unversioned Checkmk APIs; expect to adapt the package to
new Checkmk releases.

## Layout

| repo | installs to (site) | |
|---|---|---|
| `gui/wato/rule_schema_api.py` | `local/lib/python3/cmk/gui/plugins/wato/` | loader: imports the package, registers the endpoints |
| `lib/python3/rule_schema_api/` | `local/lib/python3/rule_schema_api/` | the code |

Checkmk has no plug-in namespace for REST endpoints, so the loader sits in the
Setup (`wato`) one, which the GUI imports on startup; everything else is a
normal package on the site's `sys.path`.

| module | |
|---|---|
| `endpoints.py` | the two endpoints, response schemas, registration |
| `catalog.py` | ruleset registry, display-name languages, kinds |
| `valuespec.py` | schema from a ValueSpec |
| `form_spec.py` | schema from a FormSpec (where Setup has no valuespec) |
| `example.py` | example `value_raw` from a schema |
| `_util.py` | JSON node types, small helpers |

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). In short — lint, format and type
settings are Checkmk's own (`pyproject.toml`):

```sh
pip install -r requirements-dev.txt
make lint          # ruff format --check + ruff check
make typecheck     # mypy against an installed Checkmk's sources
make test          # unit tests + site tests (an installed Checkmk, no site needed)
python3 tests/smoke_live.py http://localhost/mysite --password ... --all   # a running site
```

CI (`.github/workflows/ci.yml`) runs all of it against the newest Checkmk 2.5
and 3.0 community images, including installing the MKP into a running site.

## Build & install

```sh
python3 scripts/build_mkp.py          # -> rule_schema_api-<version>.mkp
# as the site user:
mkp add rule_schema_api-<version>.mkp
mkp enable rule_schema_api <version>
```

## License

GPL-2.0-only
