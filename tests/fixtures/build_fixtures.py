# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
tests/fixtures/build_fixtures.py (Assembly Companion) - build the test
projects: small multi-file FreeCAD projects with relative paths and known
dimensions, plus the states produced by the addon (frozen, lightweight,
selection sets, duplicated joints).

Inside FreeCAD (pytest session fixture):
    import build_fixtures; build_fixtures.build_all(out_dir, states=True)

From the command line (writes to $AC_FIXTURES_OUT):
    AC_FIXTURES_OUT=/tmp/fx freecadcmd tests/fixtures/build_fixtures.py

Projects (each in its own folder):
  basic/        plate (100x60x10, hole r5), pin (r5 x 30), block (40x40x20)
                + assembly: plate grounded, pin Revolute in the hole,
                block Fixed on the plate
  std_part/     a Std_Part "Cotes" holding two Bodies, linked into an
                assembly with a base, Fixed joint through the Part path
  subassembly/  a sub-assembly (two blocks, Fixed) inserted into a main
                assembly next to a grounded base
  collisions/   boxes A, B (overlap 500 mm3) and C (touching B only)
  revisions/    AB_001a_Plate / AB_001b_Plate (same object names) and an
                assembly using revision a
  link_array/   a bolt used by a Link array of 4 and a single Link (BOM: 5)
States (copies of basic/ unless noted):
  state_frozen/, state_lightweight/, state_selection_sets/,
  state_duplicated_joints/, state_std_part_frozen/ (copy of std_part/)
"""

import os
import shutil
import sys

import FreeCAD as App


# ----------------------------------------------------------------------
#  Geometry helpers
# ----------------------------------------------------------------------
def _body(doc, name, label=None):
    b = doc.addObject("PartDesign::Body", name)
    b.Label = label or name
    return b


def box_body(doc, name, length, width, height, label=None, placement=None):
    b = _body(doc, name, label)
    box = b.newObject("PartDesign::AdditiveBox", name + "Box")
    box.Length, box.Width, box.Height = length, width, height
    if placement is not None:
        b.Placement = placement
    return b


def plate_body(doc, name="Plate", thickness=10.0):
    b = box_body(doc, name, 100, 60, thickness)
    hole = b.newObject("PartDesign::SubtractiveCylinder", "Hole")
    hole.Radius, hole.Height = 5, thickness + 2
    hole.Placement = App.Placement(App.Vector(50, 30, -1), App.Rotation())
    return b


def pin_body(doc, name="Pin"):
    b = _body(doc, name)
    c = b.newObject("PartDesign::AdditiveCylinder", "PinCyl")
    c.Radius, c.Height = 5, 30
    return b


def find_face(shape, pred):
    for i, f in enumerate(shape.Faces, 1):
        if pred(f):
            return "Face%d" % i
    raise ValueError("face not found")


def find_edge(shape, pred):
    for i, e in enumerate(shape.Edges, 1):
        if pred(e):
            return "Edge%d" % i
    raise ValueError("edge not found")


def _top(z):
    return lambda f: abs(f.CenterOfMass.z - z) < 1e-6 and f.Surface.__class__.__name__ == "Plane"


def _circle_at(z, r):
    return lambda e: (hasattr(e.Curve, "Radius") and abs(e.Curve.Radius - r) < 1e-6
                      and abs(e.Curve.Center.z - z) < 1e-6)


# ----------------------------------------------------------------------
#  Assembly helpers
# ----------------------------------------------------------------------
def new_assembly(doc, name="Assembly"):
    import AssemblyApp  # noqa: F401  (registers Assembly::AssemblyObject)
    asm = doc.addObject("Assembly::AssemblyObject", name)
    asm.newObject("Assembly::JointGroup", "Joints")
    return asm


def joint_group(asm):
    for o in asm.Group:
        if o.isDerivedFrom("Assembly::JointGroup"):
            return o
    return asm.newObject("Assembly::JointGroup", "Joints")


def link(doc, asm, target, name, placement=None):
    lk = doc.addObject("App::Link", name)
    lk.setLink(target)
    lk.Label = name
    if placement is not None:
        lk.Placement = placement
    asm.addObject(lk)
    return lk


def ground(asm, obj):
    import JointObject
    g = joint_group(asm).newObject("App::FeaturePython", "GroundedJoint")
    JointObject.GroundedJoint(g, obj)
    return g


def joint(asm, kind, ref1, ref2, label=None):
    """Joint of type `kind` between ref1 = (obj, [sub, sub]) and ref2."""
    import JointObject
    j = joint_group(asm).newObject("App::FeaturePython", "Joint")
    j.Label = label or kind
    JointObject.Joint(j, JointObject.JointTypes.index(kind))
    j.Proxy.setJointConnectors(j, [ref1, ref2])
    return j


def _save(doc, path):
    doc.recompute()
    doc.saveAs(path)


def _close(*docs):
    for d in docs:
        try:
            App.closeDocument(d.Name)
        except Exception:
            pass


def _new(name):
    return App.newDocument(name.replace("-", "_"))


# ----------------------------------------------------------------------
#  Projects
# ----------------------------------------------------------------------
def build_basic(folder):
    os.makedirs(folder, exist_ok=True)
    d_plate = _new("plate"); plate = plate_body(d_plate); _save(d_plate, os.path.join(folder, "plate.FCStd"))
    d_pin = _new("pin"); pin = pin_body(d_pin); _save(d_pin, os.path.join(folder, "pin.FCStd"))
    d_block = _new("block"); block = box_body(d_block, "Block", 40, 40, 20)
    _save(d_block, os.path.join(folder, "block.FCStd"))

    d = _new("basic_assembly")
    d.saveAs(os.path.join(folder, "assembly.FCStd"))
    asm = new_assembly(d)
    l_plate = link(d, asm, plate, "Plate")
    l_pin = link(d, asm, pin, "Pin", App.Placement(App.Vector(50, 30, -10), App.Rotation()))
    l_block = link(d, asm, block, "Block", App.Placement(App.Vector(5, 5, 10), App.Rotation()))
    d.recompute()
    ground(asm, l_plate)
    ps, pins, bs = plate.Shape, pin.Shape, block.Shape
    hole_top = find_edge(ps, _circle_at(10, 5))
    pin_bottom = find_edge(pins, _circle_at(0, 5))
    joint(asm, "Revolute", (l_plate, [hole_top, hole_top]), (l_pin, [pin_bottom, pin_bottom]),
          "Revolute")
    plate_top = find_face(ps, _top(10))
    block_bottom = find_face(bs, _top(0))
    joint(asm, "Fixed", (l_plate, [plate_top, plate_top]), (l_block, [block_bottom, block_bottom]),
          "Fixed")
    _save(d, d.FileName)
    _close(d, d_plate, d_pin, d_block)


def build_std_part(folder):
    os.makedirs(folder, exist_ok=True)
    d_c = _new("cotes")
    part = d_c.addObject("App::Part", "Cotes")
    left = box_body(d_c, "Left", 20, 60, 30)
    right = box_body(d_c, "Right", 20, 60, 30, placement=App.Placement(App.Vector(80, 0, 0),
                                                                         App.Rotation()))
    part.addObject(left)
    part.addObject(right)
    _save(d_c, os.path.join(folder, "cotes.FCStd"))
    d_b = _new("base"); base = box_body(d_b, "Base", 100, 60, 10)
    _save(d_b, os.path.join(folder, "base.FCStd"))

    d = _new("std_part_assembly")
    d.saveAs(os.path.join(folder, "assembly.FCStd"))
    asm = new_assembly(d)
    l_base = link(d, asm, base, "Base")
    l_cotes = link(d, asm, part, "Cotes", App.Placement(App.Vector(0, 0, 10), App.Rotation()))
    d.recompute()
    ground(asm, l_base)
    top = find_face(base.Shape, _top(10))
    left_bottom = "Left." + find_face(left.Shape, _top(0))
    joint(asm, "Fixed", (l_base, [top, top]), (l_cotes, [left_bottom, left_bottom]), "Fixed")
    _save(d, d.FileName)
    _close(d, d_c, d_b)


def build_subassembly(folder):
    os.makedirs(folder, exist_ok=True)
    d_a = _new("sub_a"); a = box_body(d_a, "BlockA", 30, 30, 30); _save(d_a, os.path.join(folder, "block_a.FCStd"))
    d_b = _new("sub_b"); b = box_body(d_b, "BlockB", 30, 30, 10); _save(d_b, os.path.join(folder, "block_b.FCStd"))
    d_s = _new("sub"); d_s.saveAs(os.path.join(folder, "sub.FCStd"))
    sub = new_assembly(d_s, "SubAssembly")
    la = link(d_s, sub, a, "BlockA")
    lb = link(d_s, sub, b, "BlockB", App.Placement(App.Vector(0, 0, 30), App.Rotation()))
    d_s.recompute()
    ground(sub, la)
    joint(sub, "Fixed", (la, [find_face(a.Shape, _top(30))] * 2),
          (lb, [find_face(b.Shape, _top(0))] * 2), "Fixed")
    _save(d_s, d_s.FileName)
    d_base = _new("sub_base"); base = box_body(d_base, "Base", 100, 100, 10)
    _save(d_base, os.path.join(folder, "base.FCStd"))
    d = _new("main"); d.saveAs(os.path.join(folder, "main.FCStd"))
    asm = new_assembly(d)
    l_base = link(d, asm, base, "Base")
    link(d, asm, sub, "Sub", App.Placement(App.Vector(10, 10, 10), App.Rotation()))
    d.recompute()
    ground(asm, l_base)
    _save(d, d.FileName)
    _close(d, d_base, d_s, d_a, d_b)


def build_collisions(folder):
    """A [0,10]^3, B shifted 5 in X (common volume 500 mm3), C from x=15
    (touches B on a face, no common volume)."""
    os.makedirs(folder, exist_ok=True)
    d = _new("collisions"); d.saveAs(os.path.join(folder, "collisions.FCStd"))
    asm = new_assembly(d)
    for name, x in (("A", 0), ("B", 5), ("C", 15)):
        b = box_body(d, name, 10, 10, 10, placement=App.Placement(App.Vector(x, 0, 0),
                                                                   App.Rotation()))
        asm.addObject(b)
    _save(d, d.FileName)
    _close(d)


def build_revisions(folder):
    os.makedirs(folder, exist_ok=True)
    for rev, thick in (("a", 10.0), ("b", 15.0)):
        dr = _new("rev_" + rev)
        plate_body(dr, "Plate", thick)
        _save(dr, os.path.join(folder, "AB_001%s_Plate.FCStd" % rev))
        _close(dr)
    d_base = _new("rev_base"); base = box_body(d_base, "Base", 150, 100, 5)
    _save(d_base, os.path.join(folder, "base.FCStd"))
    d_a = App.openDocument(os.path.join(folder, "AB_001a_Plate.FCStd"))
    plate = d_a.getObject("Plate")
    d = _new("rev_assembly"); d.saveAs(os.path.join(folder, "assembly.FCStd"))
    asm = new_assembly(d)
    l_base = link(d, asm, base, "Base")
    l_plate = link(d, asm, plate, "Plate", App.Placement(App.Vector(0, 0, 5), App.Rotation()))
    d.recompute()
    ground(asm, l_base)
    joint(asm, "Fixed", (l_base, [find_face(base.Shape, _top(5))] * 2),
          (l_plate, [find_face(plate.Shape, _top(0))] * 2), "Fixed")
    _save(d, d.FileName)
    _close(d, d_a, d_base)


def build_link_array(folder):
    os.makedirs(folder, exist_ok=True)
    d_b = _new("bolt"); bolt = pin_body(d_b, "Bolt"); _save(d_b, os.path.join(folder, "bolt.FCStd"))
    d = _new("array"); d.saveAs(os.path.join(folder, "assembly.FCStd"))
    asm = new_assembly(d)
    arr = link(d, asm, bolt, "BoltArray")
    arr.ElementCount = 4
    link(d, asm, bolt, "BoltSingle", App.Placement(App.Vector(100, 0, 0), App.Rotation()))
    _save(d, d.FileName)
    _close(d, d_b)


# ----------------------------------------------------------------------
#  States produced by the addon
# ----------------------------------------------------------------------
def _copy(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _components(asm):
    return [o for o in asm.Group if o.isDerivedFrom("App::Link")]


def build_states(root):
    from freecad.assembly_companion import freeze, lightweight, duplicate
    from freecad.assembly_companion import selection_sets as ss

    def open_asm(folder, name="assembly.FCStd"):
        d = App.openDocument(os.path.join(root, folder, name))
        d.recompute()
        return d, d.getObject("Assembly")

    _copy(os.path.join(root, "basic"), os.path.join(root, "state_frozen"))
    d, asm = open_asm("state_frozen")
    freeze.figer(d, None)
    _save(d, d.FileName)
    _close(*App.listDocuments().values())

    _copy(os.path.join(root, "std_part"), os.path.join(root, "state_std_part_frozen"))
    d, asm = open_asm("state_std_part_frozen")
    freeze.figer(d, None)
    _save(d, d.FileName)
    _close(*App.listDocuments().values())

    _copy(os.path.join(root, "basic"), os.path.join(root, "state_lightweight"))
    d, asm = open_asm("state_lightweight")
    lightweight.make(d, _components(asm))
    _save(d, d.FileName)
    _close(*App.listDocuments().values())

    _copy(os.path.join(root, "basic"), os.path.join(root, "state_selection_sets"))
    d, asm = open_asm("state_selection_sets")
    ss.create_set(d, "Parts", ["Assembly|Plate.", "Assembly|Pin."])
    ss.create_set(d, "Faces", ["Assembly|Plate.Face6", "Assembly|Block.Edge1"])
    _save(d, d.FileName)
    _close(*App.listDocuments().values())

    _copy(os.path.join(root, "basic"), os.path.join(root, "state_duplicated_joints"))
    d, asm = open_asm("state_duplicated_joints")
    duplicate.duplicate(d, [d.getObject("Pin")], with_joints=True)
    _save(d, d.FileName)
    _close(*App.listDocuments().values())


def build_all(out, states=True):
    """Build every project (and the addon states) under `out`."""
    os.makedirs(out, exist_ok=True)
    build_basic(os.path.join(out, "basic"))
    build_std_part(os.path.join(out, "std_part"))
    build_subassembly(os.path.join(out, "subassembly"))
    build_collisions(os.path.join(out, "collisions"))
    build_revisions(os.path.join(out, "revisions"))
    build_link_array(os.path.join(out, "link_array"))
    if states:
        build_states(out)
    return out


# freecadcmd runs a script under the name of its file, not "__main__": run
# when this file is the script on the command line, not when imported
if os.environ.get("AC_FIXTURES_OUT") and any(a.endswith("build_fixtures.py") for a in sys.argv):
    code = 0
    try:
        build_all(os.environ["AC_FIXTURES_OUT"],
                  states=os.environ.get("AC_FIXTURES_STATES", "1") == "1")
        print("fixtures built in", os.environ["AC_FIXTURES_OUT"])
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
