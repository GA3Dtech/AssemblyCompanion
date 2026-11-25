# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Panel models on real documents: OK is one undo step, Cancel (the model
never run) leaves the document unchanged."""

import os

import pytest

from conftest import open_doc, reopen

pytestmark = pytest.mark.freecad


def _outdated_doc(project):
    from freecad.assembly_companion import api
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    api.freeze_parts(doc)
    doc = reopen(doc)
    future = os.path.getmtime(os.path.join(folder, "plate.FCStd")) + 3600
    os.utime(os.path.join(folder, "plate.FCStd"), (future, future))
    doc.UndoMode = 1
    return doc


def test_outdated_panel_accept_is_one_undo_step(project):
    from freecad.assembly_companion import outdated
    doc = _outdated_doc(project)
    undo = doc.UndoCount
    m = outdated.OutdatedPanel(doc)
    assert len(m.get("parts")) == 1
    assert m.run("refreeze") is True and len(m.result) == 1
    assert doc.UndoCount == undo + 1


def test_outdated_panel_cancel_changes_nothing(project):
    from freecad.assembly_companion import outdated
    doc = _outdated_doc(project)
    undo = doc.UndoCount
    before = {o.Name: o.FigeDate for o in doc.Objects if hasattr(o, "FigeDate")}
    m = outdated.OutdatedPanel(doc)
    m.set_row_checked("parts", m.get("parts")[0], False)
    assert doc.UndoCount == undo
    assert {o.Name: o.FigeDate for o in doc.Objects if hasattr(o, "FigeDate")} == before


def test_new_part_panel_creates_one_file_cancel_creates_none(project, tmp_path):
    import FreeCAD as App
    from freecad.assembly_companion import new_part, prefs
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    plate = [o for o in doc.Objects if o.Label == "Plate"][0]
    out = tmp_path / "new_parts"
    out.mkdir()
    saved = prefs.get("NewPartLastDir"), prefs.get("NewPartLastPrefix")
    try:
        prefs.put("NewPartLastDir", str(out))
        prefs.put("NewPartLastPrefix", "ZZ")
        cancelled = new_part.NewPartPanel(doc, [(plate, "")])
        cancelled.set("description", "Never")
        assert os.listdir(str(out)) == []          # Cancel = the model never runs
        m = new_part.NewPartPanel(doc, [(plate, "")])
        m.set("description", "Cover")
        m.set("insert", False)
        assert m.run("create") is True, m.error
        assert [f for f in os.listdir(str(out)) if f.endswith(".FCStd")] == ["ZZ_001a_Cover.FCStd"]
        assert m.result["inserted"] is None
        App.closeDocument(m.result["document"])
    finally:
        prefs.put("NewPartLastDir", saved[0])
        prefs.put("NewPartLastPrefix", saved[1])


def test_new_file_with_and_without_container_and_body(tmp_path):
    import FreeCAD as App
    from freecad.assembly_companion import api, errors
    r = api.new_file(str(tmp_path / "AB_001a_Bracket.FCStd"), part="Bracket", body="Bracket")
    d = App.getDocument(r["document"])
    part, body = d.getObject(r["part"]), d.getObject(r["body"])
    assert part.TypeId == "App::Part" and part.Label == "Bracket"
    assert body.isDerivedFrom("PartDesign::Body") and body.getParentGeoFeatureGroup() is part
    assert os.path.isfile(r["path"])
    App.closeDocument(d.Name)
    r = api.new_file(str(tmp_path / "AB_002a.FCStd"), body="Solo")
    d = App.getDocument(r["document"])
    assert r["part"] is None and d.getObject(r["body"]).getParentGeoFeatureGroup() is None
    App.closeDocument(d.Name)
    r = api.new_file(str(tmp_path / "AB_003a.FCStd"))
    assert r["part"] is None and r["body"] is None
    App.closeDocument(r["document"])
    with pytest.raises(errors.UnsupportedObjectError):
        api.new_file(str(tmp_path / "AB_001a_Bracket.FCStd"))
