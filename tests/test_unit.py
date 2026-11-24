# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Tests that need no Checkmk: kinds, example values, helpers.

python3 -m unittest discover -s tests -p "test_unit*.py"
"""

from __future__ import annotations

import sys
import unittest
from enum import StrEnum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib" / "python3"))

from rule_schema_api._util import first, iterable, jsonable, text
from rule_schema_api.catalog import KNOWN_KINDS, parameter_names, ruleset_kind
from rule_schema_api.example import example_from_node


class TestRulesetKind(unittest.TestCase):
    def test_known_prefixes(self) -> None:
        cases = {
            "checkgroup_parameters:filesystem": "service_parameters",
            "static_checks:filesystem": "enforced_services",
            "discovery_parameters:discovery_alertmanager": "discovery",
            "agent_config:mk_logwatch": "agent_config",
            "special_agents:aws": "special_agents",
            "active_checks:http": "active_checks",
            "extra_service_conf:check_interval": "service_monitoring",
            "extra_host_conf:notification_options": "host_monitoring",
            "notification_parameters:mail": "notification_parameters",
            "inv_parameters:inv_if": "inventory",
        }
        for name, kind in cases.items():
            with self.subTest(name=name):
                self.assertEqual(ruleset_kind(name), kind)

    def test_no_prefix_is_general(self) -> None:
        self.assertEqual(ruleset_kind("host_groups"), "general")
        self.assertEqual(ruleset_kind("host_groups", "monconf/various"), "general")

    def test_discovery_group_without_prefix_is_discovery(self) -> None:
        # 2.5 names its discovery rulesets without the 3.0 prefix.
        self.assertEqual(ruleset_kind("ntp_discovery", "checkparams/discovery"), "discovery")

    def test_known_prefix_wins_over_group(self) -> None:
        self.assertEqual(
            ruleset_kind("checkgroup_parameters:x", "checkparams/discovery"), "service_parameters"
        )

    def test_unknown_prefix_is_reported_as_itself(self) -> None:
        self.assertEqual(ruleset_kind("some_new_prefix:x"), "some_new_prefix")

    def test_known_kinds_are_unique(self) -> None:
        self.assertEqual(len(KNOWN_KINDS), len(set(KNOWN_KINDS)))


class TestExampleFromNode(unittest.TestCase):
    def test_dictionary_keeps_required_keys_only(self) -> None:
        node = {
            "type": "dictionary",
            "elements": [
                {"key": "levels", "required": True, "schema": {"type": "integer", "min": 5}},
                {"key": "optional", "required": False, "schema": {"type": "string"}},
            ],
        }
        self.assertEqual(example_from_node(node), {"levels": 5})

    def test_cascading_takes_first_choice(self) -> None:
        node = {
            "type": "cascading",
            "choices": [
                {"value": "no_levels", "schema": {"type": "fixed", "value": None}},
                {"value": "fixed", "schema": {"type": "tuple", "elements": []}},
            ],
        }
        self.assertEqual(example_from_node(node), ("no_levels", None))

    def test_timespecific_is_the_plain_value(self) -> None:
        node = {"type": "timespecific", "element": {"type": "float", "min": 1}}
        self.assertEqual(example_from_node(node), 1.0)

    def test_scalars(self) -> None:
        self.assertEqual(example_from_node({"type": "string"}), "")
        self.assertIs(example_from_node({"type": "boolean"}), False)
        self.assertEqual(example_from_node({"type": "list"}), [])
        self.assertEqual(example_from_node({"type": "labels"}), {})
        self.assertIsNone(example_from_node({"type": "unknown"}))

    def test_bool_min_is_not_a_number(self) -> None:
        self.assertEqual(example_from_node({"type": "integer", "min": True}), 0)

    def test_placeholders_where_empty_is_rejected(self) -> None:
        self.assertEqual(example_from_node({"type": "string", "min_length": 1}), "example")
        self.assertEqual(example_from_node({"type": "string", "min_length": 10}), "examplexxx")
        self.assertEqual(
            example_from_node({"type": "string", "format": "url"}), "https://example.com"
        )
        self.assertEqual(
            example_from_node({"type": "string", "format": "url", "protocols": ["http"]}),
            "http://example.com",
        )
        self.assertEqual(
            example_from_node({"type": "string", "format": "email"}), "user@example.com"
        )

    def test_choice_skips_the_please_select_entry(self) -> None:
        node = {"type": "choice", "choices": [{"value": None}, {"value": "a"}]}
        self.assertEqual(example_from_node(node), "a")

    def test_lists_and_multiple_choices(self) -> None:
        element = {"type": "string", "min_length": 1}
        self.assertEqual(
            example_from_node({"type": "list", "element": element, "min_items": 1}), ["example"]
        )
        node = {"type": "multiple_choice", "choices": [{"value": "x"}, {"value": "y"}]}
        self.assertEqual(example_from_node(node), ["x"])

    def test_preconfigured_values(self) -> None:
        self.assertEqual(
            example_from_node({"type": "proxy"}), ("cmk_postprocessed", "environment_proxy", "")
        )
        self.assertEqual(
            example_from_node({"type": "time_period"}),
            ("cmk_postprocessed", "stored_time_period", "24X7"),
        )

    def test_malformed_nodes_do_not_raise(self) -> None:
        self.assertIsNone(example_from_node(None))
        self.assertEqual(example_from_node({"type": "dictionary", "elements": "x"}), {})
        self.assertIsNone(example_from_node({"type": "cascading", "choices": []}))


class TestHelpers(unittest.TestCase):
    def test_first(self) -> None:
        self.assertEqual(first(range(5), 3), ([0, 1, 2], True))
        self.assertEqual(first(range(3), 3), ([0, 1, 2], False))

    def test_jsonable(self) -> None:
        self.assertEqual(jsonable(3), 3)
        self.assertEqual(jsonable(("a", 1)), "('a', 1)")

    def test_jsonable_unwraps_enum_members(self) -> None:
        class Kind(StrEnum):
            MULTIPLE = "multiple_services"

        value = jsonable(Kind.MULTIPLE)
        self.assertEqual(value, "multiple_services")
        self.assertIs(type(value), str)  # its repr must be a Python literal

    def test_text_strips_tags(self) -> None:
        self.assertEqual(text("<b>Levels</b> for <i>x</i> "), "Levels for x")
        self.assertIsNone(text("  "))

    def test_iterable_rejects_strings(self) -> None:
        self.assertEqual(list(iterable("abc")), [])
        self.assertEqual(list(iterable([1, 2])), [1, 2])

    def test_parameter_names(self) -> None:
        def fn(a: int, b: int = 0, *, c: int = 0) -> None:
            del a, b, c

        self.assertEqual(parameter_names(fn), ("a", "b", "c"))
        self.assertEqual(parameter_names(42), ())


if __name__ == "__main__":
    unittest.main()
