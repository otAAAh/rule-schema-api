<!-- SPDX-License-Identifier: GPL-2.0-only -->
# checkmk-rule-schema-explorer

A Checkmk extension package (MKP, **Checkmk 2.5+**) that adds two endpoints to
the site's own REST API, plus a Setup page to browse them.

The rules endpoints take a rule's value as `value_raw`, a Python literal
string, but nothing in the API says what that value may contain. This package
lists every ruleset and describes the shape of its value.

## Endpoints

Both live under `/<site>/check_mk/api/1.0`, use the normal REST API
authentication, and need the `wato.use` + `wato.rulesets` permissions. They
appear in the API documentation as **Rule schemas**.

| Method | Path | Returns |
|---|---|---|
| GET | `/domain-types/rule_schema/collections/all[?include_deprecated=true]` | every ruleset |
| GET | `/objects/rule_schema/{ruleset_name}` | one ruleset's value schema |

Each collection entry has `ruleset_name`, `display_name_en` (English title),
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

## Setup page

**Setup › General › Rule schema explorer** (`wato.py?mode=rule_schema_explorer`,
`&ruleset=<name>` deep-links): search the rulesets, view a schema tree, copy
the example `value_raw` or a `curl` call.

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

## Build & install

```sh
python3 scripts/build_mkp.py          # -> rule_schema_explorer-<version>.mkp
# as the site user:
mkp add rule_schema_explorer-<version>.mkp
mkp enable rule_schema_explorer <version>
```

## License

GPL-2.0-only
