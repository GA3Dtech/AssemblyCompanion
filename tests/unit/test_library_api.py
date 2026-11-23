# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""api.scan_library / api.list_library: JSON results, explorer cache kept in step."""

import json
import os

import pytest

from freecad.assembly_companion import api, errors, library, prefs

pytestmark = pytest.mark.unit


@pytest.fixture
def lib(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    for rel in ("A/a1.FCStd", "A/a2.FCStd", "B/C/c1.FCStd"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).touch()
    cache = tmp_path / "cache"
    (cache / "thumbs").mkdir(parents=True)
    monkeypatch.setattr(library, "cache_dir", lambda: str(cache))
    old = prefs.get("LocalMasterDir")
    prefs.put("LocalMasterDir", str(root))
    yield str(root)
    prefs.put("LocalMasterDir", old)


def test_scan_library_default_folder(lib):
    res = api.scan_library()
    json.dumps(res)
    assert res["folder"] == lib and res["count"] == 3
    assert [os.path.relpath(f["folder"], lib) for f in res["folders"]] == \
        ["A", os.path.join("B", "C")]
    assert res["folders"][0]["files"][0]["name"] == "a1"


def test_list_library_uses_cache_then_targeted_scan_updates_it(lib):
    api.scan_library()
    (open(os.path.join(lib, "A", "a3.FCStd"), "wb")).close()
    assert api.list_library()["count"] == 3            # cache, no walk
    res = api.scan_library(os.path.join(lib, "A"), recursive=False)
    assert res["count"] == 3                           # only folder A
    assert api.list_library()["count"] == 4            # merged into the cache


def test_list_library_without_cache_scans(lib):
    assert api.list_library()["count"] == 3


def test_missing_folder(lib):
    with pytest.raises(errors.SourceNotFoundError):
        api.scan_library(os.path.join(lib, "nope"))
