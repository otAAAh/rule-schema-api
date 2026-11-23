#!/usr/bin/env python3
# Copyright (C) 2026 Benjamin Knapp
# SPDX-License-Identifier: GPL-2.0-only
"""Build the rule_schema_explorer MKP using only the standard library.

One part: ``gui.tar`` - ``gui/`` relative to the site's
``local/lib/python3/cmk/gui/plugins`` (the GUI imports
``wato/rule_schema_explorer`` on startup, which registers the REST endpoints).

An MKP is a gzipped tar of ``info`` (the manifest as a Python literal),
``info.json`` and one inner tar per part - cmk_mkp_tool's format, without
importing any cmk package. Same layout as checkmk-json-agent's builder.
"""

from __future__ import annotations

import io
import json
import pprint
import tarfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PARTS = {"gui": REPO / "gui"}


def _shipped_files(base: Path) -> list[Path]:
    return sorted(
        p
        for p in base.rglob("*")
        if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts
    )


def _add_bytes(tar: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    tar.addfile(info, io.BytesIO(content))


def _inner_tar(files: list[Path], base: Path) -> bytes:
    """Uncompressed tar, arcnames relative to ``base``, unowned, read-only."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for file in files:
            info = tar.gettarinfo(str(file), arcname=str(file.relative_to(base)))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            with file.open("rb") as handle:
                tar.addfile(info, handle)
    return buffer.getvalue()


def build() -> Path:
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    project, mkp = data["project"], data["tool"]["mkp"]
    version = project["version"]
    files: dict[str, list[str]] = {}
    part_tars: list[tuple[str, bytes]] = []
    for part, base in PARTS.items():
        shipped = _shipped_files(base)
        if not shipped:
            raise SystemExit(f"Nothing to package under {base.relative_to(REPO)}/")
        files[part] = [str(f.relative_to(base)) for f in shipped]
        part_tars.append((f"{part}.tar", _inner_tar(shipped, base)))

    manifest = {
        "title": mkp["title"],
        "name": mkp["package_name"],
        "description": project["description"],
        "version": version,
        "version.packaged": f"checkmk-rule-schema-explorer {version}",
        "version.min_required": mkp["min_required"],
        "version.usable_until": mkp.get("usable_until"),
        "author": mkp["author"],
        "download_url": mkp["download_url"],
        "files": files,
    }
    output = REPO / f"{mkp['package_name']}-{version}.mkp"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        _add_bytes(tar, "info", (pprint.pformat(manifest) + "\n").encode())
        _add_bytes(tar, "info.json", json.dumps(manifest).encode())
        for name, content in part_tars:
            _add_bytes(tar, name, content)
    output.write_bytes(buffer.getvalue())
    return output


if __name__ == "__main__":
    print(build())
