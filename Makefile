# SPDX-License-Identifier: GPL-2.0-only
RUFF   ?= ruff
PYTHON ?= python3

# An installed Checkmk version: its python3 runs mypy and the site tests, and its
# cmk sources are what mypy checks against. Defaults to the newest under
# /omd/versions; in CI the Checkmk container provides it.
CMK_VERSION_DIR ?= $(lastword $(sort $(filter-out %/default,$(wildcard /omd/versions/*))))
CMK_PYTHON      := $(CMK_VERSION_DIR)/bin/python3
# mypy runs under the Checkmk python, installed next to the checkout (not into
# the version directory, which is read-only).
MYPY_VERSION    := $(shell sed -n 's/^mypy==//p' requirements-dev.txt)
TOOLS_DIR       := .cmksrc/tools

# Keep these in lock-step with .github/workflows/ci.yml: the local targets must
# be a SUPERSET of what CI enforces, never a subset.
RUFF_SOURCES = gui lib scripts tests
MYPY_SOURCES = lib/python3/rule_schema_api gui/wato/rule_schema_api.py scripts

.PHONY: help format lint typecheck test test-unit test-site mkp changelog release-notes clean

help:
	@echo "Targets: format | lint | typecheck | test (test-unit + test-site) | mkp | changelog | release-notes | clean"
	@echo "Checkmk used for typecheck/test-site: $(CMK_VERSION_DIR)"

format:
	$(RUFF) format $(RUFF_SOURCES)

lint:
	$(RUFF) format --check $(RUFF_SOURCES)
	$(RUFF) check $(RUFF_SOURCES)

# Installed Checkmk ships no py.typed, so mypy would treat every cmk import as
# untyped. Exposing its sources through a symlink lets mypy read them as code.
typecheck:
	@test -x "$(CMK_PYTHON)" || { echo "No Checkmk python at $(CMK_PYTHON) - set CMK_VERSION_DIR" >&2; exit 1; }
	mkdir -p .cmksrc
	ln -sfn $(wildcard $(CMK_VERSION_DIR)/lib/python3*/site-packages/cmk) .cmksrc/cmk
	test -d $(TOOLS_DIR)/mypy || $(CMK_PYTHON) -m pip install -q --disable-pip-version-check --target $(TOOLS_DIR) mypy==$(MYPY_VERSION)
	MYPYPATH=.cmksrc PYTHONPATH=$(TOOLS_DIR) $(CMK_PYTHON) -m mypy $(MYPY_SOURCES)

test: test-unit test-site

test-unit:
	$(PYTHON) -m unittest discover -s tests -p "test_unit*.py" -v

test-site:
	@test -x "$(CMK_PYTHON)" || { echo "No Checkmk python at $(CMK_PYTHON) - set CMK_VERSION_DIR" >&2; exit 1; }
	$(CMK_PYTHON) -m unittest discover -s tests -p "test_site*.py" -v

mkp:
	$(PYTHON) scripts/build_mkp.py

# Regenerate CHANGELOG.md from the git history (one section per version).
changelog:
	$(PYTHON) scripts/gen_changelog.py

# Print the release notes for the current pyproject version (release body).
release-notes:
	$(PYTHON) scripts/gen_changelog.py --version $$($(PYTHON) -c 'import tomllib,pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')

clean:
	rm -rf *.mkp .cmksrc
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
