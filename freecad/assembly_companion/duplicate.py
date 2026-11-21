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
(preference DuplicateJoints: ask / always / never): each joint is copied and
every reference to an original component is pointed to its clone - the
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


def _copy_joint(doc, joint, mapping):
    new = doc.copyObject(joint, False)
    new.Label = joint.Label
    for p in joint.InList:          # the "Joints" group of the assembly
        if p.hasExtension("App::GroupExtension") and joint in p.Group:
            p.addObject(new)
            break
    for prop in new.PropertiesList:
        try:
            t = new.getTypeIdOfProperty(prop)
        except Exception:
            continue
        if "LinkSub" in t:
            refs = freeze._lire(new, prop, t)
            if not refs:
                continue
            new_refs = []
            for base, subs in refs:
                if base is None:
                    new_refs.append((base, subs))
                    continue
                b2, subs2 = base, []
                for sub in subs:
                    b2, s2 = _remap_ref(base, sub, mapping)
                    subs2.append(s2)
                new_refs.append((b2, subs2))
            # Cleared first: FreeCAD would keep the hidden topological names
            # computed on the original component
            setattr(new, prop, [] if "List" in t else None)
            freeze._ecrire(new, prop, t, new_refs)
        elif "Link" in t:
            v = getattr(new, prop)
            if v in mapping:
                setattr(new, prop, mapping[v])
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
            new_joints = [_copy_joint(doc, j, mapping) for j in joints]
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
