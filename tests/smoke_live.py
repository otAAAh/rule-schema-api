#!/usr/bin/env python3
# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Smoke-test the endpoints over HTTP on a running site with the package installed.

    python3 tests/smoke_live.py http://localhost:5000/cmk --user cmkadmin --password ...
    python3 tests/smoke_live.py ... --all            # also fetch every ruleset's schema
    python3 tests/smoke_live.py ... --language de    # also check translated names

``--language`` switches the user's GUI language for the check and restores the
previous one afterwards. Stdlib only, so it runs on any Python 3.12+.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request

_LIST = "/domain-types/rule_schema/collections/all"


class Site:
    def __init__(self, base: str, user: str, password: str) -> None:
        self.api = base.rstrip("/") + "/check_mk/api/1.0"
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._auth = f"Basic {token}"
        self.user = user

    def request(
        self, path: str, *, method: str = "GET", body: object = None, etag: str | None = None
    ) -> tuple[int, object, str | None]:
        headers = {"Authorization": self._auth, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if etag is not None:
            headers["If-Match"] = etag
        req = urllib.request.Request(self.api + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, json.loads(resp.read() or b"null"), resp.headers.get("ETag")
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"null"), None

    def get(self, path: str) -> tuple[int, object]:
        status, payload, _ = self.request(path)
        return status, payload

    def set_language(self, language: str) -> str:
        """Set the user's GUI language; return the previous one.

        The user record's ETag changes with every request of that user (it
        tracks the last activity), so a PUT can lose the race against our own
        GET: retry on 412 with a fresh ETag.
        """
        path = f"/objects/user_config/{self.user}"
        status = 0
        for _ in range(5):
            _, payload, etag = self.request(path)
            previous = str(_dig(payload, "extensions", "language") or "en")
            status, _, _ = self.request(path, method="PUT", body={"language": language}, etag=etag)
            if status != 412:
                break
        _expect(status == 200, f"setting language {language!r} returned HTTP {status}")
        return previous


def _say(message: str) -> None:
    sys.stdout.write(message + "\n")


class SmokeError(Exception):
    pass


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def _dig(payload: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(payload, dict):
            return None
        payload = payload.get(key)
    return payload


def _entries(site: Site, query: str = "") -> list[dict[str, object]]:
    status, payload = site.get(_LIST + query)
    _expect(status == 200, f"GET {_LIST}{query} returned HTTP {status}: {payload}")
    value = _dig(payload, "value")
    _expect(isinstance(value, list), f"no 'value' list in {_LIST}{query}")
    assert isinstance(value, list)
    return [e for e in value if isinstance(e, dict)]


def check_collection(site: Site) -> list[dict[str, object]]:
    entries = _entries(site)
    _expect(len(entries) > 1000, f"only {len(entries)} rulesets listed")
    for entry in entries:
        for key in ("ruleset_name", "display_name_en", "kind", "group"):
            _expect(key in entry, f"{entry.get('ruleset_name')}: missing {key!r}")
    _say(f"ok   collection: {len(entries)} rulesets")
    return entries


def check_kind_filter(site: Site, entries: list[dict[str, object]]) -> None:
    wanted = {"service_parameters", "discovery"}
    filtered = _entries(site, "?kind=service_parameters&kind=discovery")
    returned = {e["kind"] for e in filtered}
    _expect(returned <= wanted, f"kind filter returned other kinds: {returned - wanted}")
    expected = sum(1 for e in entries if e["kind"] in wanted)
    _expect(len(filtered) == expected, f"kind filter: {len(filtered)} != {expected}")
    _expect(_entries(site, "?kind=no_such_kind") == [], "unknown kind is not empty")
    _say(f"ok   kind filter: {len(filtered)} service_parameters + discovery")


def check_object(site: Site) -> None:
    status, payload = site.get("/objects/rule_schema/checkgroup_parameters:filesystem")
    _expect(status == 200, f"filesystem schema returned HTTP {status}")
    _expect(_dig(payload, "kind") == "service_parameters", "filesystem: wrong kind")
    _expect(isinstance(_dig(payload, "schema", "type"), str), "filesystem: no schema type")
    status, payload = site.get("/objects/rule_schema/does_not_exist")
    _expect(status == 404, f"unknown ruleset returned HTTP {status}")
    _say("ok   object: filesystem schema, 404 for an unknown ruleset")


def check_all_schemas(site: Site, entries: list[dict[str, object]]) -> None:
    failures = []
    for entry in entries:
        name = str(entry["ruleset_name"])
        status, payload = site.get(f"/objects/rule_schema/{name}")
        if status != 200 or _dig(payload, "kind") != entry["kind"]:
            failures.append(f"{name}: HTTP {status}")
    _expect(not failures, f"{len(failures)} schemas failed: {failures[:10]}")
    _say(f"ok   all schemas: {len(entries)} x HTTP 200, kinds match")


def check_language(site: Site, language: str) -> None:
    previous = site.set_language(language)
    try:
        entries = _entries(site, "?kind=discovery")
        _expect(all("display_name" in e for e in entries), "display_name missing")
        translated = sum(1 for e in entries if e["display_name"] != e["display_name_en"])
        _expect(translated > 0, f"no discovery ruleset translated to {language!r}")
    finally:
        site.set_language(previous)
    english = _entries(site, "?kind=discovery")
    _expect(not any("display_name" in e for e in english), "display_name for an English user")
    _say(f"ok   language {language}: {translated}/{len(entries)} translated, restored {previous}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base", help="site URL, e.g. http://localhost:5000/cmk")
    parser.add_argument("--user", default="cmkadmin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--all", action="store_true", help="fetch every ruleset's schema")
    parser.add_argument("--language", help="also check translated names in this language")
    args = parser.parse_args()

    site = Site(args.base, args.user, args.password)
    try:
        entries = check_collection(site)
        check_kind_filter(site, entries)
        check_object(site)
        if args.language:
            check_language(site, args.language)
        if args.all:
            check_all_schemas(site, entries)
    except SmokeError as err:
        sys.stderr.write(f"FAIL {err}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
