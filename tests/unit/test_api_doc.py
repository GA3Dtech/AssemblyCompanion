# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""docs/api.md lists every public function and is up to date with the code;
describe() covers __all__ and is JSON-serialisable."""

import inspect
import json
import os
import subprocess
import sys

import pytest

from freecad.assembly_companion import api

pytestmark = pytest.mark.unit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_describe_covers_all_public_functions():
    info = api.describe()
    json.dumps(info)
    public = [n for n in api.__all__ if inspect.isfunction(getattr(api, n, None))]
    assert [f["name"] for f in info["functions"]] == public
    assert all(f["doc"] for f in info["functions"])


def test_api_md_lists_every_function():
    with open(os.path.join(ROOT, "docs", "api.md"), encoding="utf-8") as fh:
        text = fh.read()
    for f in api.describe()["functions"]:
        assert "### `%s(" % f["name"] in text, f["name"]


def test_api_md_up_to_date():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "api_doc.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
