# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import STEP as part: the import groups become Parts, every element is
shown by the assembly at its place, can carry joints and be frozen."""

import os

import pytest

from conftest import close_all, open_doc, reopen

pytestmark = pytest.mark.freecad

App = pytest.importorskip("FreeCAD")


def _api():
    from freecad.assembly_companion import api
    return api


def _centres(shape):
    return sorted((round(s.Volume, 2),) + tuple(round(c, 2) for c in s.CenterOfMass)
                  for s in shape.Solids)


@pytest.fixture
def step_file(tmp_path):
    """multi-body STEP: Boitier, Fil and a nested group holding Ame, placed."""
    import Import
    import Part
    d = App.newDocument("step_make")
    top = d.addObject("App::Part", "MD650")
    a = d.addObject("Part::Feature", "Boitier")
    a.Shape = Part.makeBox(10, 20, 5)
    f = d.addObject("Part::Feature", "Fil")
    f.Shape = Part.makeCylinder(1, 30, App.Vector(2, 2, 5))
    sub = d.addObject("App::Part", "Ames")
    sub.Placement = App.Placement(App.Vector(30, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90))
    m = d.addObject("Part::Feature", "Ame")
    m.Shape = Part.makeBox(2, 3, 8)
    sub.addObject(m)
    for o in (a, f, sub):
        top.addObject(o)
    d.recompute()
    expected = _centres(Part.getShape(top))
    path = str(tmp_path / "MD650-0.9-5_12x34.step")
    Import.export([top], path)
    App.closeDocument(d.Name)
    return path, expected


def _main(doc):
    return doc.getObject("Assembly")


def test_import_as_new_file(project, step_file):
    import Part
    api = _api()
    path, expected = step_file
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    n_before = len(Part.getShape(_main(doc)).Solids)
    res = api.import_step(doc, path)
    assert res["file"] == os.path.join(folder, "MD650-0.9-5_12x34.FCStd")
    assert res["solids"] == 3 and os.path.isfile(res["file"])
    src = App.getDocument(res["document"])
    assert not [o for o in src.Objects if o.TypeId == "App::LinkGroup"]
    part = src.getObject(res["part"])
    assert _centres(Part.getShape(part, transform=False)) == expected
    link = doc.getObject(res["inserted"])
    assert link.getParentGeoFeatureGroup() is _main(doc)
    shown = Part.getShape(_main(doc))
    assert len(shown.Solids) == n_before + 3
    doc.save()
    doc = reopen(doc)
    assert len(Part.getShape(_main(doc)).Solids) == n_before + 3


def test_import_into_the_assembly_document(project, step_file):
    import Part
    api = _api()
    path, expected = step_file
    doc = open_doc(os.path.join(project("basic"), "assembly.FCStd"))
    res = api.import_step(doc, path, mode="document")
    assert res["file"] is None and res["solids"] == 3
    part = doc.getObject(res["part"])
    assert part.getParentGeoFeatureGroup() is _main(doc)
    assert not [o for o in doc.Objects if o.TypeId == "App::LinkGroup"]
    assert _centres(Part.getShape(part, transform=False)) == expected


def test_joint_on_an_imported_element_then_freeze(project, step_file):
    import build_fixtures as bf
    api = _api()
    path, _expected = step_file
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    res = api.import_step(doc, path)
    link = doc.getObject(res["inserted"])
    src = App.getDocument(res["document"])
    boitier = [o for o in src.Objects if o.Label == "Boitier"][0]
    plate = doc.getObject("Plate")
    top = bf.find_face(plate.LinkedObject.Shape, bf._top(10))
    bottom = bf.find_face(boitier.Shape, bf._top(0))
    path_in_part, p = [boitier.Name], boitier.getParentGeoFeatureGroup()
    while p is not None and p.Name != res["part"]:       # nested Parts of the STEP
        path_in_part.insert(0, p.Name)
        p = p.getParentGeoFeatureGroup()
    sub = ".".join(path_in_part) + "." + bottom
    bf.joint(_main(doc), "Fixed", (plate, [top] * 2), (link, [sub] * 2), "PlateToStep")
    doc.recompute()
    d = api.diagnose(doc)
    assert d["broken"] == 0, [r for r in d["references"] if not r["ok"]]
    assert _main(doc).solve() == 0
    res2 = api.freeze_parts(doc, [link.Name])
    assert res2["frozen"] == [link.Name]
    doc.save()
    close_all()
    os.remove(res["file"])
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    assert api.diagnose(doc)["broken"] == 0


def test_existing_file_is_never_overwritten(project, step_file):
    from freecad.assembly_companion import errors
    api = _api()
    path, _expected = step_file
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    target = os.path.join(folder, "MD650-0.9-5_12x34.FCStd")
    open(target, "wb").close()
    with pytest.raises(errors.UnsupportedObjectError):
        api.import_step(doc, path)
    assert os.path.getsize(target) == 0
