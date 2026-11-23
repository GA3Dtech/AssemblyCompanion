# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""BOM, collisions and archive, through the API."""

import csv
import json
import os
import zipfile

import pytest

from conftest import close_all, open_doc

pytestmark = pytest.mark.freecad

EXPECTED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "expected")


def _api():
    from freecad.assembly_companion import api
    return api


def _expected(name):
    with open(os.path.join(EXPECTED, name), encoding="utf-8", newline="") as fh:
        return [{"quantity": int(r["quantity"]), "part": r["part"],
                 "source_file": r["source_file"], "state": r["state"]}
                for r in csv.DictReader(fh)]


@pytest.mark.parametrize("folder, file, expected, freeze", [
    ("basic", "assembly.FCStd", "bom_basic.csv", False),
    ("basic", "assembly.FCStd", "bom_basic_frozen.csv", True),
    ("std_part", "assembly.FCStd", "bom_std_part.csv", False),
    ("subassembly", "main.FCStd", "bom_subassembly.csv", False),
    ("link_array", "assembly.FCStd", "bom_link_array.csv", False),
])
def test_bom(project, folder, file, expected, freeze):
    api = _api()
    doc = open_doc(os.path.join(project(folder), file))
    if freeze:
        api.freeze_parts(doc)
    rows = api.bom(doc)
    json.dumps(rows)
    assert rows == _expected(expected)


def test_collisions(project):
    api = _api()
    doc = open_doc(os.path.join(project("collisions"), "collisions.FCStd"))
    res = api.check_collisions(doc)
    assert res["parts"] == 3
    assert len(res["pairs"]) == 1                       # B touching C is not reported
    pair = res["pairs"][0]
    assert {pair["a"], pair["b"]} == {"A", "B"}
    assert abs(pair["volume"] - 500.0) < 1e-3
    res = api.check_collisions(doc, show=True)
    assert doc.getObject("AC_Collisions") is not None


def test_archive_reopens_elsewhere(project, tmp_path):
    api = _api()
    doc = open_doc(os.path.join(project("basic"), "assembly.FCStd"))
    z = str(tmp_path / "out.zip")
    res = api.archive(doc, z)
    assert sorted(res["files"]) == ["assembly.FCStd", "block.FCStd", "pin.FCStd",
                                    "plate.FCStd"]
    with zipfile.ZipFile(z) as f:
        assert "MANIFEST.txt" in f.namelist()
        f.extractall(str(tmp_path / "x"))
    close_all()
    doc = open_doc(str(tmp_path / "x" / "assembly.FCStd"))
    assert api.diagnose(doc)["broken"] == 0
    for n in ("Plate", "Pin", "Block"):
        t = doc.getObject(n).LinkedObject
        assert t is not None and t.Document.FileName.startswith(str(tmp_path / "x"))
