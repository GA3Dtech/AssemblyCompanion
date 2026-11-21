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
touched; joints are not copied (the clone is free, ready to be dragged or
joined).

User-facing texts are in English, translated through i18n.tr().
"""

import FreeCAD as App

from . import freeze
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


def duplicate(doc=None, comps=None):
    """Clone the selected assembly components. Returns the clones."""
    import FreeCADGui as Gui
    doc = doc or App.ActiveDocument
    if comps is None:
        comps = freeze.selection_composants()
    if not comps:
        raise RuntimeError(tr("Select one or more components of the assembly "
                              "(in the tree, or a face in the 3D view)."))
    doc.openTransaction(tr("Duplicate components"))
    try:
        clones = [_clone(doc, c) for c in comps]
        doc.recompute()
    finally:
        doc.commitTransaction()
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
