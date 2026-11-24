# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Tests against a real Checkmk version: every ruleset, both languages, kinds.

Run with an installed version's interpreter; no site user is needed:

    /omd/versions/<version>/bin/python3 -m unittest discover -s tests -p "test_site*.py"

The GUI needs a site directory to write to, so this builds a throwaway one in
a temporary directory (the version's ``share``/``lib``/``bin`` symlinked in,
empty writable ``etc``/``var``/``tmp``/``local``) and loads the whole GUI into
it. Without Checkmk on the interpreter the tests are skipped.
"""

from __future__ import annotations

import collections
import os
import sys
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib" / "python3"))

_VERSION_ROOT = Path(sys.executable).resolve().parent.parent
_HAS_CMK = (_VERSION_ROOT / "share" / "omd").is_dir() or (
    _VERSION_ROOT / "share" / "check_mk"
).is_dir()

# Rulesets that cannot build a schema in a throwaway site because they read
# site state that does not exist there (core config, BI files). They work on a
# real site; checked there by fetching every schema over HTTP.
_THROWAWAY_SITE_FAILURES = {
    "special_agents:bi",
    "extra_host_conf:check_interval",
    "extra_host_conf:retry_interval",
    "host_check_commands",
}
# Valuespec/FormSpec classes the walkers do not describe yet (a few fields).
_ALLOWED_UNKNOWN = {"IconSelector", "AbsoluteDate"}


def _make_site() -> Path:
    root = Path(tempfile.mkdtemp(prefix="rule-schema-api-site-"))
    for name in ("share", "lib", "bin"):
        (root / name).symlink_to(_VERSION_ROOT / name)
    for name in ("etc", "var", "tmp", "local"):
        (root / name).mkdir()
    # Default values and some rulesets read the site's OMD settings.
    (root / "etc" / "omd").mkdir()
    (root / "etc" / "omd" / "site.conf").write_text(
        "CONFIG_CORE='cmc'\nCONFIG_APACHE_TCP_PORT='5000'\nCONFIG_AGENT_RECEIVER_PORT='8000'\n"
        "CONFIG_AUTOMATION_HELPER='on'\nCONFIG_TMPFS='on'\nCONFIG_MKEVENTD='on'\n"
        "CONFIG_LIVEPROXYD='on'\nCONFIG_PIGGYBACK_HUB='off'\nCONFIG_TRACE_SEND='off'\n"
    )
    return root


def _walk(node: object) -> Iterator[dict[str, object]]:
    if not isinstance(node, dict):
        return
    yield node
    for key in ("element", "schema"):
        yield from _walk(node.get(key))
    for key in ("elements", "choices"):
        children = node.get(key)
        if isinstance(children, list):
            for child in children:
                yield from _walk(child)


@unittest.skipUnless(_HAS_CMK, "needs an installed Checkmk version's python3")
class TestAgainstCheckmk(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Before any cmk import: cmk.utils.paths reads OMD_ROOT at import time.
        os.environ["OMD_ROOT"] = str(_make_site())
        os.environ.setdefault("OMD_SITE", "rsetest")
        from cmk.ccc.version import edition
        from cmk.gui import main_modules

        try:  # 3.0
            from cmk.gui.wsgi.app import gui_context
        except ImportError:  # 2.5
            from cmk.gui.utils.script_helpers import gui_context
        from cmk.utils import paths

        try:  # 3.0
            main_modules.register(edition(paths.omd_root), debug=False)
        except TypeError:  # 2.5 has no 'debug' argument
            main_modules.register(edition(paths.omd_root))
        cls._context = gui_context()
        cls._context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._context.__exit__(None, None, None)

    def test_endpoints_register(self) -> None:
        import rule_schema_api
        from cmk.gui.openapi import endpoint_registry

        rule_schema_api.register()
        paths = {
            e.path for e in endpoint_registry if getattr(e, "family_name", None) == "Rule schemas"
        }
        self.assertEqual(
            paths,
            {
                "/domain-types/rule_schema/collections/all",
                "/objects/rule_schema/{ruleset_name}",
                "/objects/rule_schema/{ruleset_name}/actions/validate/invoke",
            },
        )

    def test_english_list_has_no_translated_names(self) -> None:
        from rule_schema_api.catalog import list_rulesets

        entries = list_rulesets(lang="en")
        self.assertGreater(len(entries), 1000)
        for entry in entries:
            assert isinstance(entry, dict)
            self.assertIn("ruleset_name", entry)
            self.assertIn("display_name_en", entry)
            self.assertIn("kind", entry)
            self.assertNotIn("display_name", entry)

    def test_german_list_adds_translated_names(self) -> None:
        from rule_schema_api.catalog import list_rulesets

        entries = {e["ruleset_name"]: e for e in list_rulesets(lang="de") if isinstance(e, dict)}
        self.assertTrue(all("display_name" in e for e in entries.values()))
        filesystem = entries["checkgroup_parameters:filesystem"]
        self.assertEqual(filesystem["display_name_en"], "File systems (used space and growth)")
        self.assertNotEqual(filesystem["display_name"], filesystem["display_name_en"])

    def test_kind_filter(self) -> None:
        from rule_schema_api.catalog import list_rulesets

        everything = [e for e in list_rulesets() if isinstance(e, dict)]
        wanted = frozenset({"service_parameters", "discovery"})
        filtered = [e for e in list_rulesets(kinds=wanted) if isinstance(e, dict)]
        self.assertEqual({e["kind"] for e in filtered}, wanted)
        self.assertEqual(len(filtered), sum(1 for e in everything if e["kind"] in wanted))
        self.assertEqual(list_rulesets(kinds=frozenset({"no_such_kind"})), [])

    def test_every_ruleset_has_a_schema(self) -> None:
        from rule_schema_api.catalog import list_rulesets, ruleset_schema

        failures: dict[str, str] = {}
        unknown: collections.Counter[str] = collections.Counter()
        sources: collections.Counter[str] = collections.Counter()
        for entry in list_rulesets():
            assert isinstance(entry, dict)
            name = str(entry["ruleset_name"])
            try:
                schema = ruleset_schema(name)
            except Exception as exc:
                failures[name] = repr(exc)
                continue
            sources[str(schema["schema_source"])] += 1
            for node in _walk(schema["schema"]):
                if node.get("type") == "unknown":
                    unknown[str(node.get("valuespec") or node.get("form_spec"))] += 1
        self.assertLessEqual(set(failures), _THROWAWAY_SITE_FAILURES, failures)
        self.assertLessEqual(set(unknown), _ALLOWED_UNKNOWN, unknown)
        self.assertGreater(sources["form_spec"], 0)

    def test_validate_value_raw(self) -> None:
        from cmk.gui.watolib.rulespecs import rulespec_registry
        from rule_schema_api.catalog import ruleset_schema
        from rule_schema_api.validate import validate_value_raw

        rulespec = rulespec_registry["checkgroup_parameters:filesystem"]
        example = ruleset_schema("checkgroup_parameters:filesystem")["example_value_raw"]
        assert isinstance(example, str)
        self.assertEqual(validate_value_raw(rulespec, example), [])
        problems = validate_value_raw(rulespec, "{'levels': 'not a tuple'}")
        self.assertTrue(problems)
        self.assertEqual(
            validate_value_raw(rulespec, "{'levels':")[0]["title"],  # type: ignore[index]
            "value_raw is not a Python literal",
        )

    def test_examples_pass_the_rules_api_check(self) -> None:
        """Nearly every example is accepted unchanged by the rules API's own check.

        Excluded: values the throwaway site cannot check (its core is not
        running, so checks that call it fail) and rulesets that need objects
        to exist first (host groups, contact groups, ...).
        """
        from rule_schema_api.catalog import list_rulesets, ruleset_schema

        accepted, rejected = 0, []
        for entry in list_rulesets():
            assert isinstance(entry, dict)
            name = str(entry["ruleset_name"])
            try:
                schema = ruleset_schema(name)
            except Exception:
                continue
            if schema["example_valid"] is True:
                accepted += 1
                continue
            problems = schema["example_problems"]
            assert isinstance(problems, list) and problems
            first_problem = problems[0]
            assert isinstance(first_problem, dict)
            if "Automation" in str(first_problem.get("detail")):
                continue
            rejected.append(name)
        self.assertGreater(accepted, 800)
        self.assertLess(len(rejected) / (accepted + len(rejected)), 0.05, rejected)

    def test_form_spec_example(self) -> None:
        from rule_schema_api.catalog import ruleset_schema

        schema = ruleset_schema("checkgroup_parameters:antivir_update_age")
        self.assertEqual(schema["schema_source"], "form_spec")
        self.assertEqual(schema["example_value_raw"], "{'levels': ('no_levels', None)}")


if __name__ == "__main__":
    unittest.main()
