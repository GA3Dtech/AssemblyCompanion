# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - duplicate assembly components
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
duplicate.py (Assembly Companion) - clone the selected components in the
assembly tree: each clone is a new App::Link to the same target (source file
object, frozen copy or object of the assembly file), with the same
placement, colours and scale, in the same assembly. Source files are not
touched.

Joints (and grounding) of the duplicated components can be duplicated too
(preference DuplicateJoints: ask / always / never): each joint is recreated
through the Assembly workbench API (JointObject.Joint / GroundedJoint, as its
task panel does) with every reference to an original component pointed to
its clone - the
base object of the reference (26.x joints reference the component itself,
e.g. ('Part', ['Fige_Body001.Edge116'])), a segment of the path when the
reference starts higher in the assembly, and plain links such as
ObjectToGround. A joint between two duplicated components joins the two
clones; a joint with a part that is not duplicated joins the clone to that
same part, so the clone lands exactly on the original until a joint value
(offset, distance...) is changed.

User-facing texts are in English, translated through i18n.tr().
"""

import FreeCAD as App

from . import freeze
from . import prefs
from .i18n import tr


def _parent_assembly(comp):
    """Assembly / Std_Part that directly holds `comp`, or None."""
    for p in comp.InList:
        if p.isDerivedFrom("App::Part") and comp in p.Group:
            return p
    return None


def _clone(doc, comp):
    if comp.isDerivedFrom("App::Link"):
        # copyObject keeps every property of the Link (target, placement,
        # scale, colour overrides...) without copying the target itself
        clone = doc.copyObject(comp, False)
    else:
        # A Body / solid placed directly in the assembly: link to it
        clone = doc.addObject("App::Link", comp.Name)
        clone.setLink(comp)
        clone.Placement = comp.Placement
    clone.Label = comp.Label        # FreeCAD makes it unique (…001)
    parent = _parent_assembly(comp)
    if parent is not None and clone not in parent.Group:
        parent.addObject(clone)
    return clone


# ----------------------------------------------------------------------
#  Joints
# ----------------------------------------------------------------------
def joints_of(comps):
    """Joints and groundings using any of `comps`, each once."""
    out = []
    for c in comps:
        for j in freeze.liaisons_de(c):
            if j not in out:
                out.append(j)
    return out


def _remap_ref(base, sub, mapping):
    """(base, sub) of a reference with the originals replaced by their
    clones. `mapping` = {original: clone}."""
    objets, _mapped, _elem = freeze.decouper_sub(sub)
    parts = sub.split(".")
    for comp, clone in mapping.items():
        k = freeze._index_lien(base, objets, comp)
        if k == -1:
            base = clone
        elif k is not None and k < len(parts) and parts[k] == comp.Name:
            parts[k] = clone.Name
    return base, ".".join(parts)


# Joint values copied to the new joint (references and computed connector
# placements are rebuilt by the Assembly workbench itself)
_JOINT_VALUES = ("Offset1", "Offset2", "Distance", "Distance2", "Angle",
                 "EnableLengthMin", "LengthMin", "EnableLengthMax", "LengthMax",
                 "EnableAngleMin", "AngleMin", "EnableAngleMax", "AngleMax",
                 "Detach1", "Detach2", "Suppressed")


def _remap_refs(joint, prop, mapping):
    """Reference property `prop` of `joint` with originals -> clones."""
    t = joint.getTypeIdOfProperty(prop)
    out = []
    for base, subs in freeze._lire(joint, prop, t):
        if base is None:
            continue
        b2, subs2 = base, []
        for sub in subs:
            b2, s2 = _remap_ref(base, sub, mapping)
            subs2.append(s2)
        out.append((b2, subs2))
    return out[0] if out else None


def _copy_joint(doc, joint, mapping):
    """Recreate `joint` the way the Assembly workbench creates joints (a
    plain copyObject is not rebuilt by the workbench: the copy lands at the
    root of the assembly and the solver ignores it), with every reference to
    an original pointed to its clone. Returns the new joint or None."""
    asm = None
    for p in joint.InList:
        if p.isDerivedFrom("Assembly::AssemblyObject"):
            asm = p
    if asm is None:
        return None
    return _new_joint(joint, asm, mapping.get,
                      lambda prop: _remap_refs(joint, prop, mapping))


def copy_joint_into(doc, joint, mapping, target_asm, paths):
    """Recreate `joint` of a source assembly in another assembly (a frozen
    copy): `mapping` = {source component: copy}, `paths` = the freeze path
    mapping {source name: (copy name, sub-mapping)} used to translate the
    path inside each component. Returns the new joint or None."""
    def refs(prop):
        t = joint.getTypeIdOfProperty(prop)
        out = []
        for base, subs in freeze._lire(joint, prop, t):
            if base is None:
                continue
            if base.Name in paths and base not in (joint.InList or []):
                new_base = doc.getObject(paths[base.Name][0])
                sub_paths = paths[base.Name][1]
            else:                       # reference relative to the assembly
                new_base, sub_paths = target_asm, paths
            if new_base is None:
                return None
            out.append((new_base, [freeze.reecrire_sub_chemins(s, -1, sub_paths)
                                   if sub_paths is not None else freeze.reecrire_sub(s, -1)
                                   for s in subs]))
        return out[0] if out else None
    return _new_joint(joint, target_asm, mapping.get, refs)


def _new_joint(joint, asm, target_of, refs_of):
    import JointObject
    import UtilsAssembly
    group = UtilsAssembly.getJointGroup(asm)

    if "ObjectToGround" in joint.PropertiesList:
        target = target_of(joint.ObjectToGround)
        if target is None:
            return None
        new = group.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(new, target)
        if App.GuiUp:
            JointObject.ViewProviderGroundedJoint(new.ViewObject)
        return new

    if not hasattr(joint, "JointType"):
        return None                     # rigid groups and others: not handled
    refs = [r for r in (refs_of("Reference1"), refs_of("Reference2")) if r is not None]
    if len(refs) < 2:
        return None
    new = group.newObject("App::FeaturePython", "Joint")
    new.Label = joint.Label
    JointObject.Joint(new, JointObject.JointTypes.index(joint.JointType))
    if App.GuiUp:
        JointObject.ViewProviderJoint(new.ViewObject)
    for prop in _JOINT_VALUES:
        if prop in joint.PropertiesList and prop in new.PropertiesList:
            try:
                setattr(new, prop, getattr(joint, prop))
            except Exception:
                pass
    # Detached connectors keep their own placement instead of the reference's
    for i in ("1", "2"):
        if getattr(joint, "Detach" + i, False):
            setattr(new, "Placement" + i, getattr(joint, "Placement" + i))
    # Same call as the joint task panel: sets the references, computes the
    # connector placements, pre-solves and solves the assembly
    new.Proxy.setJointConnectors(new, refs)
    new.purgeTouched()
    return new


def _ask_joints(n):
    """True when the joints must be duplicated too."""
    mode = prefs.get("DuplicateJoints")
    if mode in ("always", "never"):
        return mode == "always"
    import FreeCADGui as Gui
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    r = QtWidgets.QMessageBox.question(
        Gui.getMainWindow(), tr("Duplicate components"),
        tr("The selected components have {n} joint(s). Duplicate the joints too?\n\n"
           "Yes: each clone gets the same joints as its original (it lands on the "
           "original until a joint value is changed). The other part of each joint "
           "is then joined to the original and to the clone: for a fixed base that "
           "is fine, for a part that moves it may over-constrain it.\n"
           "No: the clones are free.")
        .format(n=n),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.Yes)
    return r == QtWidgets.QMessageBox.Yes


# ----------------------------------------------------------------------
#  Entry point
# ----------------------------------------------------------------------
def duplicate(doc=None, comps=None, with_joints=None):
    """Clone the selected assembly components (and their joints when
    `with_joints`, None = preference / question). Returns the clones."""
    import FreeCADGui as Gui
    doc = doc or App.ActiveDocument
    if comps is None:
        comps = freeze.selection_composants()
    if not comps:
        raise RuntimeError(tr("Select one or more components of the assembly "
                              "(in the tree, or a face in the 3D view)."))
    joints = joints_of(comps)
    if with_joints is None:
        with_joints = bool(joints) and _ask_joints(len(joints))
    doc.openTransaction(tr("Duplicate components"))
    try:
        clones = [_clone(doc, c) for c in comps]
        new_joints = []
        if with_joints:
            mapping = dict(zip(comps, clones))
            new_joints = [n for n in (_copy_joint(doc, j, mapping) for j in joints)
                          if n is not None]
        doc.recompute()
    finally:
        doc.commitTransaction()
    if new_joints:
        App.Console.PrintMessage(tr("Duplicate: {n} joint(s) duplicated.").format(
            n=len(new_joints)) + "\n")
    for c, n in zip(comps, clones):
        App.Console.PrintMessage(tr("Duplicate: {source} -> {clone}").format(
            source=c.Label, clone=n.Label) + "\n")
    try:
        Gui.Selection.clearSelection()
        for n in clones:
            Gui.Selection.addSelection(n)
    except Exception:
        pass
    return clones
