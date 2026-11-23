<!-- SPDX-License-Identifier: GPL-2.0-only -->
# Security Policy

## Supported versions

This is a small, single-maintainer Checkmk extension. Security fixes are made
on `main` and shipped in the next tagged release. Only the **latest release** is
supported — please reproduce any issue against it (or `main`) before reporting.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report privately via GitHub's **[Report a vulnerability](https://github.com/otAAAh/rule-schema-api/security/advisories/new)**
button (Security → Advisories) on this repository. That opens a private advisory
visible only to the maintainer.

Please include, as far as you can:

- the affected version (release tag or commit),
- a description of the issue and its impact,
- steps to reproduce or a proof of concept,
- any suggested remediation.

You can expect an initial acknowledgement within a few days. Once a fix is
available it will be released and the advisory published, crediting you unless
you prefer to remain anonymous.

## Scope

The package adds two read-only endpoints to the site's REST API. Especially
relevant areas:

- **authorization** — both endpoints require `wato.use` and `wato.rulesets`
  (`lib/python3/rule_schema_api/endpoints.py`); a way to read schemas without
  them is in scope;
- **information disclosure** — schemas include choice lists computed from the
  site's configuration (host groups, time periods, check plug-ins, ...). Any
  secret value (a password, a password-store entry's content) appearing in a
  schema or in `example_value_raw` is in scope;
- **resource use** — a request that makes the GUI process hang or exhaust
  memory (the walkers cap choice lists and recursion depth).

Issues in Checkmk itself should be reported to [Checkmk](https://checkmk.com/),
not here.
