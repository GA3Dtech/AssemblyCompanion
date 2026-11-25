# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Freezing sub-assemblies (App::Link to an assembly, Assembly::AssemblyLink
over several levels) and Std_Parts holding imported STEP groups: after the
freeze, and after the source files are deleted, the assembly shows the same
solids at the same places, its joints resolve and it solves."""

import os

import pytest

from conftest import close_all, open_doc, reopen

pytestmark = pytest.mark.freecad

App = pytest.importorskip("FreeCAD")


def _api():
    from freecad.assembly_companion import api
    return api


def main_assembly(doc):
    from freecad.assembly_companion import bom
    return [o for o in bom.roots_of(doc) if o.isDerivedFrom("Assembly::AssemblyObject")][0]


def signature(doc):
    """Volume and centre of mass of every solid the assembly shows."""
    import Part
    shape = Part.getShape(main_assembly(doc))
    return sorted((round(s.Volume, 2),) + tuple(round(c, 2) for c in s.CenterOfMass)
                  for s in shape.Solids)


def delete_sources(folder, keep):
    for f in os.listdir(folder):
        if f.endswith(".FCStd") and f != keep:
            os.remove(os.path.join(folder, f))


def check_frozen_and_alone(doc, folder, keep, before):
    api = _api()
    assert api.diagnose(doc)["broken"] == 0
    doc.save()
    close_all()
    delete_sources(folder, keep)
    doc = open_doc(os.path.join(folder, keep))
    assert [d.Name for d in App.listDocuments().values()] == [doc.Name]
    doc.recompute()
    assert not [o.Label for o in doc.Objects if "Invalid" in o.State]
    assert signature(doc) == before
    assert api.diagnose(doc)["broken"] == 0
    assert main_assembly(doc).solve() == 0
    return doc


# ----------------------------------------------------------------------
#  Sub-assembly inserted as an App::Link (FreeCAD 1.0 style)
# ----------------------------------------------------------------------
def test_link_to_subassembly_keeps_its_parts(project):
    api = _api()
    folder = project("subassembly")
    doc = open_doc(os.path.join(folder, "main.FCStd"))
    before = signature(doc)
    assert len(before) == 3
    res = api.freeze_parts(doc)
    assert sorted(res["frozen"]) == ["Base", "Sub"] and res["skipped"] == []
    assert signature(doc) == before
    doc = check_frozen_and_alone(doc, folder, "main.FCStd", before)
    rows = {r["part"]: r for r in api.bom(doc)}
    assert set(rows) == {"Base", "BlockA", "BlockB"}
    assert all(r["state"] == "frozen" for r in rows.values())


def test_frozen_subassembly_keeps_its_joints(project):
    from freecad.assembly_companion import freeze
    api = _api()
    folder = project("subassembly")
    doc = open_doc(os.path.join(folder, "main.FCStd"))
    api.freeze_parts(doc, ["Sub"])
    fa = doc.getObject("Sub").LinkedObject
    assert freeze._est_conteneur_fige(fa) and fa.isDerivedFrom("Assembly::AssemblyObject")
    group = [o for o in fa.Group if o.TypeId == "Assembly::JointGroup"][0]
    assert sorted("ObjectToGround" in j.PropertiesList for j in group.Group) == [False, True]
    assert fa.solve() == 0


def test_relink_and_refreeze_subassembly(project):
    api = _api()
    folder = project("subassembly")
    doc = open_doc(os.path.join(folder, "main.FCStd"))
    before = signature(doc)
    api.freeze_parts(doc)
    assert sorted(api.relink_parts(doc)["relinked"]) == ["Base", "Sub"]
    assert doc.getObject("Sub").LinkedObject.Document is not doc
    assert signature(doc) == before
    from freecad.assembly_companion import freeze
    copies = lambda: sorted(o.Name for o in doc.Objects if freeze._est_fige(o)
                            or freeze._est_lien_fige(o))
    n = copies()
    api.freeze_parts(doc)
    assert copies() == n                    # copies reused, nothing duplicated
    assert signature(doc) == before and api.diagnose(doc)["broken"] == 0


# ----------------------------------------------------------------------
#  Sub-assemblies of the Assembly workbench (Assembly::AssemblyLink)
# ----------------------------------------------------------------------
@pytest.fixture
def al_project(project):
    folder = project("subassembly_al")
    if not os.path.isfile(os.path.join(folder, "main.FCStd")):
        pytest.skip("this FreeCAD has no Assembly::AssemblyLink")
    return folder


def test_assembly_link_three_levels(al_project):
    from freecad.assembly_companion import freeze
    api = _api()
    doc = open_doc(os.path.join(al_project, "main.FCStd"))
    before = signature(doc)
    assert len(before) == 4                 # Base, BlockA, BlockB, Cap
    assert api.diagnose(doc)["broken"] == 0
    res = api.freeze_parts(doc)
    assert sorted(res["frozen"]) == ["Base", "Sub"], res
    al = doc.getObject("Sub")
    assert al.TypeId == "Assembly::AssemblyLink"
    assert al.LinkedObject.Document is doc and freeze._est_conteneur_fige(al.LinkedObject)
    assert signature(doc) == before
    doc = check_frozen_and_alone(doc, al_project, "main.FCStd", before)
    assert {r["part"] for r in api.bom(doc)} == {"Base", "BlockA", "BlockB", "Cap"}


def test_assembly_link_relink(al_project):
    api = _api()
    doc = open_doc(os.path.join(al_project, "main.FCStd"))
    before = signature(doc)
    api.freeze_parts(doc)
    res = api.relink_parts(doc)
    assert sorted(res["relinked"]) == ["Base", "Sub"]
    assert doc.getObject("Sub").LinkedObject.Document is not doc
    doc.recompute()
    assert signature(doc) == before and api.diagnose(doc)["broken"] == 0


def test_component_picked_inside_assembly_link_freezes_the_sub_assembly(al_project):
    from freecad.assembly_companion import freeze
    doc = open_doc(os.path.join(al_project, "main.FCStd"))
    child = doc.getObject("Sub").Group[-1]
    assert [o.Name for o in freeze.liens_externes(doc, [child])] == ["Sub"]


# ----------------------------------------------------------------------
#  Std_Part holding imported STEP groups (App::LinkGroup)
# ----------------------------------------------------------------------
def test_step_groups_freeze_without_losing_anything(project):
    api = _api()
    folder = project("step_group")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    before = signature(doc)
    assert len(before) == 6                 # Plate, Beam, Boitier, Fil, 2 x Ame
    res = api.freeze_parts(doc)
    assert sorted(res["frozen"]) == ["Group", "Plate"] and res["skipped"] == []
    assert signature(doc) == before
    labels = {o.Label for o in doc.Objects}
    assert {"Boitier", "Fil_plus_rouge", "MD650", "MD650_links"} <= labels
    doc = check_frozen_and_alone(doc, folder, "assembly.FCStd", before)


def test_step_groups_as_one_block(project):
    api = _api()
    folder = project("step_group")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    before = signature(doc)
    api.freeze_parts(doc, ["Group"], mode="block")
    copy = doc.getObject("Group").LinkedObject
    assert copy.isDerivedFrom("Part::Feature") and len(copy.Shape.Solids) == 5
    assert len(copy.FigeNomenclature) == 5
    api.freeze_parts(doc, ["Plate"])
    assert signature(doc) == before
    doc = check_frozen_and_alone(doc, folder, "assembly.FCStd", before)
    parts = {r["part"]: r["quantity"] for r in api.bom(doc)}
    assert parts == {"Plate": 1, "Beam": 1, "Boitier": 1, "Fil_plus_rouge": 1, "Ame_plus": 2}


def test_block_relink_restores_the_references(project):
    api = _api()
    folder = project("step_group")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    before = signature(doc)
    api.freeze_parts(doc, ["Group"], mode="block")
    api.relink_parts(doc, ["Group"])
    doc.recompute()
    assert doc.getObject("Group").LinkedObject.Document is not doc
    assert signature(doc) == before and api.diagnose(doc)["broken"] == 0


# ----------------------------------------------------------------------
#  Never half frozen
# ----------------------------------------------------------------------
def test_broken_member_leaves_the_link_linked(project):
    api = _api()
    folder = project("step_group")
    src = open_doc(os.path.join(folder, "pieces.FCStd"))
    src.getObject("AmeLink0").LinkedObject = None      # broken element
    src.save()
    close_all()
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    doc.UndoMode = 1
    undo = doc.UndoCount
    res = api.freeze_parts(doc, ["Group"])
    assert res["frozen"] == [] and res["skipped"][0]["name"] == "Group"
    assert "AmeLink0" in res["skipped"][0]["reason"] or "broken" in res["skipped"][0]["reason"]
    assert doc.getObject("Group").LinkedObject.Document is not doc
    assert doc.UndoCount == undo


def test_freeze_is_one_undo_step(project):
    api = _api()
    folder = project("subassembly")
    doc = open_doc(os.path.join(folder, "main.FCStd"))
    doc.UndoMode = 1
    before = signature(doc)
    api.freeze_parts(doc)
    doc.undo()
    doc.recompute()
    assert doc.getObject("Sub").LinkedObject.Document is not doc
    assert signature(doc) == before


def test_outdated_frozen_subassembly_is_refrozen(project):
    api = _api()
    folder = project("subassembly")
    doc = open_doc(os.path.join(folder, "main.FCStd"))
    api.freeze_parts(doc)
    doc = reopen(doc)
    future = os.path.getmtime(os.path.join(folder, "block_b.FCStd")) + 3600
    os.utime(os.path.join(folder, "block_b.FCStd"), (future, future))
    future = os.path.getmtime(os.path.join(folder, "sub.FCStd")) + 3600
    os.utime(os.path.join(folder, "sub.FCStd"), (future, future))
    outdated = [r["label"] for r in api.outdated_parts(doc) if r["state"] == "outdated"]
    assert "BlockB" in outdated and "SubAssembly" in outdated
    before = signature(doc)
    api.refreeze_outdated(doc)
    assert signature(doc) == before and api.diagnose(doc)["broken"] == 0


# ----------------------------------------------------------------------
#  BOM by sub-assembly and archive of every level
# ----------------------------------------------------------------------
def _tree_names(tree):
    return {r["part"]: (r["quantity"], _tree_names(r["children"])) for r in tree}


def test_hierarchical_bom_linked_and_frozen(al_project):
    api = _api()
    doc = open_doc(os.path.join(al_project, "main.FCStd"))
    expected = {"Base": (1, {}),
                "SubAssembly": (1, {"BlockA": (1, {}), "BlockB": (1, {}),
                                    "SubSub": (1, {"Cap": (1, {})})})}
    assert _tree_names(api.bom(doc, hierarchical=True)) == expected
    api.freeze_parts(doc)
    tree = api.bom(doc, hierarchical=True)
    assert _tree_names(tree) == expected
    assert all(r["state"] == "frozen" for r in tree)
    path = os.path.join(al_project, "bom.csv")
    res = api.export_bom_csv(doc, path, hierarchical=True)
    assert res["rows"] == 6
    with open(path, encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()
    assert len(lines) == 7 and lines[1].split(",")[0] == "1"


def test_archive_holds_every_level(al_project, tmp_path):
    import zipfile
    api = _api()
    doc = open_doc(os.path.join(al_project, "main.FCStd"))
    z = str(tmp_path / "pack.zip")
    res = api.archive(doc, z)
    names = sorted(os.path.basename(f) for f in res["files"])
    assert names == ["base.FCStd", "blocka.FCStd", "blockb.FCStd", "cap.FCStd",
                     "main.FCStd", "sub.FCStd", "subsub.FCStd"]
    with zipfile.ZipFile(z) as zf:
        assert len([n for n in zf.namelist() if n.endswith(".FCStd")]) == 7


# ----------------------------------------------------------------------
#  A chain of links of one body, in the file of the body (the "maillon"
#  case): the frozen sub-assembly keeps every link where it was
# ----------------------------------------------------------------------
def _maillon(doc):
    """A link plate with two holes: the joints use their circular edges,
    like a real chain."""
    import Part
    body = doc.addObject("PartDesign::Body", "maillon")
    shape = Part.makeBox(40, 10, 5).cut(Part.makeCylinder(2, 5, App.Vector(5, 5, 0))) \
        .cut(Part.makeCylinder(2, 5, App.Vector(35, 5, 0)))
    feat = body.newObject("PartDesign::FeatureBase", "Base")
    feat.BaseFeature = doc.addObject("Part::Feature", "maillon_shape")
    feat.BaseFeature.Shape = shape
    doc.recompute()
    return body


def _hole_edge(shape, x, z):
    for i, e in enumerate(shape.Edges):
        curve = e.Curve
        c = (getattr(curve, "Location", None) or curve.Center) if "Circle" in curve.TypeId else None
        if c is not None and abs(c.x - x) < 1e-6 and abs(c.z - z) < 1e-6:
            return "Edge%d" % (i + 1)
    raise AssertionError("hole edge not found")


def test_chain_of_links_keeps_its_shape(tmp_path):
    import build_fixtures as bf
    api = _api()
    folder = str(tmp_path)
    d = App.newDocument("maillon")
    d.saveAs(os.path.join(folder, "maillon.FCStd"))
    body = _maillon(d)
    sub = bf.new_assembly(d)
    links = [bf.link(d, sub, body, "maillon%03d" % (i + 1),
                     App.Placement(App.Vector(30 * i, 0, 5 * i), App.Rotation()))
             for i in range(4)]
    d.recompute()
    bf.ground(sub, links[0])
    end, start = _hole_edge(body.Shape, 35, 5), _hole_edge(body.Shape, 5, 0)
    for a, b in zip(links, links[1:]):
        bf.joint(sub, "Revolute", (a, [end] * 2), (b, [start] * 2), "Revolute")
    # Moved apart after the joints were made, as in a sub-assembly never
    # solved in this state: the frozen copy must keep the placements as
    # they are (re-solving would stack the links)
    for i, lk in enumerate(links[1:], 1):
        lk.Placement = App.Placement(App.Vector(60 * i, 15 * i, -8 * i),
                                     App.Rotation(App.Vector(0, 0, 1), 25 * i))
    d.recompute()
    d.save()
    m = App.newDocument("main_chain")
    m.saveAs(os.path.join(folder, "main.FCStd"))
    asm = bf.new_assembly(m)
    bf.link(m, asm, sub, "Assembly001", App.Placement(App.Vector(-6, 0, 0), App.Rotation()))
    m.recompute()
    m.save()
    before = signature(m)
    assert len(before) == 4
    api.freeze_parts(m)
    m.recompute()
    assert signature(m) == before
    check_frozen_and_alone(m, folder, "main.FCStd", before)


# ----------------------------------------------------------------------
#  A Body holding only a SubShapeBinder (made by "New part from
#  selection"): its Tip gives no shape, the frozen copy must still show it
# ----------------------------------------------------------------------
def test_body_with_only_a_binder_stays_visible(tmp_path):
    import Part
    import build_fixtures as bf
    api = _api()
    folder = str(tmp_path)
    src = App.newDocument("binder_part")
    body = src.addObject("PartDesign::Body", "Body")
    body.Placement = App.Placement(App.Vector(50, 0, 0), App.Rotation())
    binder = body.newObject("PartDesign::SubShapeBinder", "Binder")
    binder.BindMode = "Detached"
    binder.Shape = Part.makeBox(10, 20, 5)
    src.recompute()
    src.saveAs(os.path.join(folder, "part.FCStd"))
    assert body.Shape.isNull()
    m = App.newDocument("binder_main")
    m.saveAs(os.path.join(folder, "main.FCStd"))
    asm = bf.new_assembly(m)
    bf.link(m, asm, body, "Part", App.Placement(App.Vector(0, 30, 0), App.Rotation()))
    m.recompute()
    m.save()
    # The Link shows the binder at its own placement: centre (5, 40, 2.5)
    expected = [(1000.0, 5.0, 40.0, 2.5)]
    res = api.freeze_parts(m)
    assert res["frozen"] == ["Part"]
    m.recompute()
    assert signature(m) == expected
    m.save()
    close_all()
    os.remove(os.path.join(folder, "part.FCStd"))
    m = open_doc(os.path.join(folder, "main.FCStd"))
    assert signature(m) == expected
