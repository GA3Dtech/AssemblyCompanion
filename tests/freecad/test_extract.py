# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Extract body: the new file opens alone, recomputes without error, and the
shape (volume, faces) is that of the original body; binders become
detached; the body can be replaced in its assembly, joints kept."""

import os

import pytest

from conftest import close_all, open_doc

pytestmark = pytest.mark.freecad

App = pytest.importorskip("FreeCAD")


def _api():
    from freecad.assembly_companion import api
    return api


def make_messy(folder):
    """A file with an assembly holding a local body whose tree uses a
    spreadsheet, a datum plane, a pocket and a binder of another body."""
    import Part
    import Sketcher
    import build_fixtures as bf
    doc = App.newDocument("messy")
    doc.saveAs(os.path.join(folder, "messy.FCStd"))
    sheet = doc.addObject("Spreadsheet::Sheet", "Params")
    sheet.set("A1", "12")
    sheet.setAlias("A1", "height")
    other = bf.box_body(doc, "Other", 40, 40, 5)
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = "Bracket"
    sk = body.newObject("Sketcher::SketchObject", "Sketch")
    sk.AttachmentSupport = [(body.Origin.OriginFeatures[3], "")]   # XY plane
    sk.MapMode = "FlatFace"
    pts = [App.Vector(0, 0, 0), App.Vector(30, 0, 0), App.Vector(30, 20, 0),
           App.Vector(0, 20, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = sk
    pad.setExpression("Length", "Params.height")
    plane = body.newObject("PartDesign::Plane", "DatumPlane")
    plane.AttachmentSupport = [(body.Origin.OriginFeatures[3], "")]
    plane.MapMode = "FlatFace"
    plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 12), App.Rotation())
    sk2 = body.newObject("Sketcher::SketchObject", "Sketch001")
    sk2.AttachmentSupport = [(plane, "")]
    sk2.MapMode = "FlatFace"
    sk2.addGeometry(Part.Circle(App.Vector(15, 10, 0), App.Vector(0, 0, 1), 4))
    pocket = body.newObject("PartDesign::Pocket", "Pocket")
    pocket.Profile = sk2
    pocket.Length = 5
    binder = body.newObject("PartDesign::SubShapeBinder", "Binder")
    binder.Support = [(other, "")]
    asm = bf.new_assembly(doc)
    asm.addObject(body)
    lo = bf.link(doc, asm, other, "OtherLink")
    doc.recompute()
    bf.ground(asm, body)
    bf.joint(asm, "Fixed", (body, [bf.find_face(body.Shape, bf._top(12))] * 2),
             (lo, [bf.find_face(other.Shape, bf._top(0))] * 2), "BodyToOther")
    doc.recompute()
    doc.save()
    return doc


def test_extracted_file_stands_alone(tmp_path):
    api = _api()
    folder = str(tmp_path)
    doc = make_messy(folder)
    body = doc.getObject("Body")
    volume, faces = body.Shape.Volume, len(body.Shape.Faces)
    dry = api.extract_bodies(doc, ["Body"], folder=folder, prefix="AB", revision="a",
                             dry_run=True)
    assert not os.listdir(folder) == [] and dry["dry_run"]
    res = api.extract_bodies(doc, ["Body"], folder=folder, prefix="AB", revision="a")
    r = res["bodies"][0]
    assert os.path.basename(r["file"]) == "AB_001a_Bracket.FCStd"
    assert {"Pad", "Pocket", "Sketch", "Sketch001", "DatumPlane", "Params"} <= set(r["copied"])
    assert any("binder" in line for line in r["standalone"])
    assert r["external"] == [] and r["invalid"] == []
    close_all()
    nd = open_doc(r["file"])
    assert [d.Name for d in App.listDocuments().values()] == [nd.Name]
    nd.recompute()
    assert not [o.Label for o in nd.Objects if "Invalid" in o.State]
    nb = nd.getObject(r["new_body"])
    assert abs(nb.Shape.Volume - volume) < 1e-6 and len(nb.Shape.Faces) == faces
    assert nd.getDependentDocuments() == [nd]
    sheet = [o for o in nd.Objects if o.TypeId == "Spreadsheet::Sheet"][0]
    pad = [o for o in nd.Objects if o.TypeId == "PartDesign::Pad"][0]
    assert pad.ExpressionEngine, "expression lost"
    assert sheet.Name in pad.ExpressionEngine[0][1], pad.ExpressionEngine
    assert sheet in pad.OutList                     # the copied sheet drives the pad
    origins = [o for o in nd.Objects if o.TypeId == "App::Origin"]
    assert len(origins) == 1, [(o.Name, [p.Name for p in o.InList]) for o in origins]



def test_replace_body_in_assembly(tmp_path):
    api = _api()
    folder = str(tmp_path)
    doc = make_messy(folder)
    res = api.extract_bodies(doc, ["Body"], folder=folder, prefix="AB", replace=True)
    assert len(res["replaced"]) == 1
    link = doc.getObject(res["replaced"][0])
    assert link.LinkedObject.Document is not doc and doc.getObject("Body") is None
    assert api.diagnose(doc)["broken"] == 0
    assert doc.getObject("Assembly").solve() == 0
