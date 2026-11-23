# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Replace, duplicate, lightweight, new part, selection sets (API)."""

import json
import os

import pytest

from conftest import App, open_doc, reopen

pytestmark = pytest.mark.freecad


def _api():
    from freecad.assembly_companion import api
    return api


def test_replace_by_next_revision_keeps_joints(project):
    api = _api()
    from freecad.assembly_companion import replace
    folder = project("revisions")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    src = doc.getObject("Plate").LinkedObject.Document.FileName
    proposed = replace.next_revision(src)
    assert os.path.basename(proposed) == "AB_001b_Plate.FCStd"
    res = api.replace_component(doc, "Plate", proposed)
    assert res["replaced"] == ["Plate"]
    t = doc.getObject("Plate").LinkedObject
    assert os.path.basename(t.Document.FileName) == "AB_001b_Plate.FCStd"
    assert api.diagnose(doc)["broken"] == 0


def test_replace_frozen_refreezes_from_new_file(project):
    api = _api()
    folder = project("revisions")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    api.freeze_parts(doc)
    res = api.replace_component(doc, "Plate", os.path.join(folder, "AB_001b_Plate.FCStd"))
    assert res["refrozen"] == ["Plate"]
    t = doc.getObject("Plate").LinkedObject
    assert t.FigeFichier.endswith("AB_001b_Plate.FCStd")
    assert abs(t.Shape.BoundBox.ZLength - 15.0) < 1e-6      # revision b is 15 thick
    doc = reopen(doc)
    assert api.diagnose(doc)["broken"] == 0


def test_duplicate_with_joints(project):
    api = _api()
    doc = open_doc(os.path.join(project("basic"), "assembly.FCStd"))
    res = api.duplicate_components(doc, ["Pin"], with_joints=True)
    json.dumps(res)
    clone = doc.getObject(res["clones"][0]["clone"])
    assert clone.Placement.isSame(doc.getObject("Pin").Placement, 1e-6)
    assert len(res["joints"]) == 1
    j = doc.getObject(res["joints"][0])
    bases = {j.Reference1[0].Name, j.Reference2[0].Name}
    assert clone.Name in bases and "Pin" not in bases
    assert any(g.isDerivedFrom("Assembly::JointGroup") for g in j.InList)
    assert doc.getObject("Assembly").solve() == 0


def _live_links_to_heavy(doc):
    """Properties of lightweight containers that link to another object."""
    from freecad.assembly_companion import lightweight
    bad = []
    for c in doc.Objects:
        if not lightweight.is_lightweight(c):
            continue
        for p in c.PropertiesList:
            if "Link" in c.getTypeIdOfProperty(p) and p not in ("Group", "Origin"):
                if getattr(c, p):
                    bad.append(p)
    return bad


def test_lightweight_has_no_live_link_and_restores(project):
    api = _api()
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    api.freeze_parts(doc, ["Pin"])                 # one frozen, two linked
    res = api.make_lightweight(doc)
    assert sorted(res["lightweight"]) == ["Block", "Pin", "Plate"]
    assert _live_links_to_heavy(doc) == []
    from freecad.assembly_companion import lightweight
    skins = [o for o in doc.Objects if lightweight._is_skin(o)]
    assert skins and all(o.TypeId == "Mesh::Feature" and o.LodPixels > 0 for o in skins)
    skeletons = sorted(r["sub"].split(".")[0] for r in api.diagnose(doc)["references"])
    assert len(set(skeletons)) >= 2                # Skeleton, Skeleton001...: real names
    doc = reopen(doc)
    # nothing heavy loaded: only the assembly itself is open
    assert [d.Name for d in App.listDocuments().values()] == [doc.Name]
    assert api.diagnose(doc)["broken"] == 0
    assert doc.getObject("Assembly").solve() == 0
    r = api.restore_full(doc)
    assert sorted(r["restored"]) == ["Block", "Pin", "Plate"]
    assert r["refrozen"] == ["Pin"]
    from freecad.assembly_companion import freeze
    assert freeze._est_fige(doc.getObject("Pin").LinkedObject)
    assert doc.getObject("Plate").LinkedObject.Document is not doc
    assert api.diagnose(doc)["broken"] == 0


def test_lightweight_restores_after_moving_the_project(project):
    """The stored source path is absolute: once the project folder is moved
    (or copied to another computer) the source is found next to the
    assembly."""
    import shutil
    api = _api()
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    api.make_lightweight(doc)
    doc.save()
    App.closeDocument(doc.Name)
    moved = folder + "_moved"
    shutil.move(folder, moved)
    doc = open_doc(os.path.join(moved, "assembly.FCStd"))
    r = api.restore_full(doc)
    assert sorted(r["restored"]) == ["Block", "Pin", "Plate"]
    assert os.path.dirname(doc.getObject("Plate").LinkedObject.Document.FileName) == moved


def test_new_part_detached_and_inserted(project):
    api = _api()
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    from build_fixtures import find_face, _top
    top = find_face(doc.getObject("Plate").LinkedObject.Shape, _top(10))
    path = os.path.join(folder, "AB_001a_Cover.FCStd")
    res = api.new_part_from_selection(doc, [["Assembly", "Plate." + top]], path, label="Cover")
    assert os.path.isfile(path) and res["inserted"]
    nd = App.getDocument(res["document"])
    binder = nd.getObject(res["binder"])
    assert binder.BindMode == "Detached" and not binder.Support
    assert not binder.Shape.isNull()
    assert doc.FileName not in [d.FileName for d in nd.getDependentDocuments() if d is not nd]
    doc.getDependentDocuments()                    # raises if the graph is not a DAG
    doc.recompute()
    assert not [o.Label for o in doc.Objects if "Invalid" in o.State]


def test_selection_sets_roundtrip(project):
    api = _api()
    doc = open_doc(os.path.join(project("basic"), "assembly.FCStd"))
    api.create_selection_set(doc, "A", ["Assembly|Plate.", "Assembly|Pin."])
    api.create_selection_set(doc, "B", ["Assembly|Pin.", "Assembly|Block.Face1"])
    doc = reopen(doc)
    sets = {s["label"]: s for s in api.selection_sets(doc)}
    assert sets["A"]["members"] == ["Assembly|Plate.", "Assembly|Pin."]
    a, b = sets["A"]["name"], sets["B"]["name"]
    inter = api.combine_selection_sets(doc, a, b, "intersection", "I")
    assert inter["members"] == ["Assembly|Pin."]
    diff = api.combine_selection_sets(doc, a, b, "difference", "D")
    assert diff["members"] == ["Assembly|Plate."]
    union = api.combine_selection_sets(doc, a, b, "union", "U")
    assert "Assembly|Block.Face1" in union["members"]


def test_fasteners_group(project):
    pytest.importorskip("FastenersCmd")
    pytest.skip("needs a Fasteners fixture (workbench present): not built yet")


def test_describe_covers_the_api():
    api = _api()
    d = api.describe()
    json.dumps(d)
    names = {f["name"] for f in d["functions"]}
    public = {n for n in api.__all__ if callable(getattr(api, n)) and
              not isinstance(getattr(api, n), type)}
    assert public <= names
