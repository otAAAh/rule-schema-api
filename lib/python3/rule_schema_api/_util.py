# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Types and small helpers shared by the schema walkers."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

# Choice lists can be huge (all host groups, all timeperiods, ...) and some are
# computed from live config. A schema lists the first ones and says so (``truncated``).
MAX_CHOICES = 200
# Valuespec trees are finite, but a buggy third-party one could recurse.
MAX_DEPTH = 40

type JsonScalar = None | bool | int | float | str
type Json = JsonScalar | list[Json] | dict[str, Json]
# One schema node: {"type": ..., "title": ..., "help": ..., <kind-specific keys>}.
type Node = dict[str, Json]

_TAG_RE = re.compile(r"<[^>]+>")


def text(value: object) -> str | None:
    """A title/help as plain text (HTML objects and tags flattened)."""
    if value is None:
        return None
    flat = _TAG_RE.sub("", str(value)).strip()
    return flat or None


def safe[T, D](fn: Callable[[], T], default: D) -> T | D:
    """``fn()``, or ``default`` if it raises.

    Titles, choices and defaults come from live configuration and third-party
    packages; one failing lookup must not fail the whole schema.
    """
    try:
        return fn()
    except Exception:
        return default


def call(obj: object, method: str) -> object:
    """``obj.<method>()`` if ``obj`` has such a method, else None (never raises)."""
    bound = getattr(obj, method, None)
    if not callable(bound):
        return None
    return safe(bound, None)


def python_literal(value: object) -> str:
    """The value as a ``value_raw`` string (the REST API takes a Python literal)."""
    return repr(value)


def first[T](items: Iterable[T], limit: int) -> tuple[list[T], bool]:
    """The first ``limit`` items, and whether there were more."""
    result: list[T] = []
    for item in items:
        if len(result) == limit:
            return result, True
        result.append(item)
    return result, False


def jsonable(value: object) -> JsonScalar:
    """Choice values are arbitrary Python; keep JSON scalars, repr the rest."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return python_literal(value)


def iterable(value: object) -> Iterable[object]:
    """``value`` if it is a non-string iterable, else nothing."""
    if isinstance(value, Iterable) and not isinstance(value, str | bytes):
        return value
    return ()
