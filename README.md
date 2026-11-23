<!-- SPDX-License-Identifier: GPL-2.0-only -->
# rule-schema-api

A Checkmk extension package (MKP, **Checkmk 2.5+**) that adds two endpoints to
the site's own REST API. API only - no GUI.

The rules endpoints take a rule's value as `value_raw`, a Python literal
string, but nothing in the API says what that value may contain. This package
lists every ruleset and describes the shape of its value.

## Endpoints

Both live under `/<site>/check_mk/api/1.0`, use the normal REST API
authentication, and need the `wato.use` + `wato.rulesets` permissions. They
appear in the API documentation as **Rule schemas**.

| Method | Path | Returns |
|---|---|---|
| GET | `/domain-types/rule_schema/collections/all[?kind=...][&include_deprecated=true]` | every ruleset, optionally filtered by kind |
| GET | `/objects/rule_schema/{ruleset_name}` | one ruleset's value schema |

Each collection entry has `ruleset_name`, `kind`, `display_name_en` (English title),
`group`, `group_display_name_en`, `match_type`, `item_type`, `is_deprecated`
and `is_form_spec`. When the requesting user's language is **not** English,
`display_name` and `group_display_name` (translated) are added.

The object adds the item schema, `schema` (a node tree: `type`, `title`,
`help`, plus `elements` / `element` / `choices` / `min` / `max` / `unit` ...
where they apply), `schema_source` (`valuespec` or `form_spec`) and an
`example_value_raw` to start from.

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

An unknown prefix is reported as the prefix itself.

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

Lint, format and type settings are Checkmk's own (see `pyproject.toml`).

```sh
ruff format gui lib scripts tests && ruff check gui lib scripts tests
# mypy against an installed Checkmk's code (it has no py.typed, so expose its
# sources through a symlink):
mkdir -p /tmp/cmksrc && ln -sfn /omd/versions/<version>/lib/python3*/site-packages/cmk /tmp/cmksrc/cmk
MYPYPATH=/tmp/cmksrc mypy --python-executable /omd/versions/<version>/bin/python3 \
    lib/python3/rule_schema_api gui/wato/rule_schema_api.py scripts/build_mkp.py

python3 -m unittest discover -s tests -p "test_unit*.py"     # no Checkmk needed
/omd/versions/<version>/bin/python3 -m unittest discover -s tests -p "test_site*.py"
```

`test_site*.py` loads the whole GUI of an installed Checkmk version (in a
throwaway site directory, so it needs no site user) and walks every ruleset.

## Build & install

```sh
python3 scripts/build_mkp.py          # -> rule_schema_api-<version>.mkp
# as the site user:
mkp add rule_schema_api-<version>.mkp
mkp enable rule_schema_api <version>
```

## License

GPL-2.0-only
