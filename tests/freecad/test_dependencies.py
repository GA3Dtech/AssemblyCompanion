# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Check dependencies: the files an assembly depends on, directly and
through another file, with the objects that use them; saving a dependency."""

import os

import pytest

from conftest import open_doc

pytestmark = pytest.mark.freecad

App = pytest.importorskip("FreeCAD")


def test_direct_and_indirect_dependencies(project):
    from freecad.assembly_companion import api
    folder = project("subassembly")
    doc = open_doc(os.path.join(folder, "main.FCStd"))
    rows = {os.path.basename(r["file"]): r for r in api.analyze_dependencies(doc)}
    assert set(rows) == {"base.FCStd", "sub.FCStd", "block_a.FCStd", "block_b.FCStd"}
    assert rows["base.FCStd"]["used_by"] == ["Base"] and rows["base.FCStd"]["via"] == ""
    assert rows["block_a.FCStd"]["used_by"] == [] and rows["block_a.FCStd"]["via"]
    import json
    json.dumps(rows)


def test_frozen_assembly_has_no_dependency(project):
    from freecad.assembly_companion import api
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    api.freeze_parts(doc)
    assert api.analyze_dependencies(doc) == [] or \
        all(not r["used_by"] for r in api.analyze_dependencies(doc))


def test_save_dependency(project):
    from freecad.assembly_companion import api
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    plate = [r for r in api.analyze_dependencies(doc) if r["label"] == "plate"
             or r["file"].endswith("plate.FCStd")][0]
    before = os.path.getmtime(plate["file"])
    os.utime(plate["file"], (before - 100, before - 100))
    assert api.save_dependencies(doc, [plate["document"]]) == [plate["document"]]
    assert os.path.getmtime(plate["file"]) > before - 100
