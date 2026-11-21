# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - group Fasteners workbench parts with their body
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
fasteners.py (Assembly Companion) - put the screws, nuts, inserts... of the
Fasteners workbench into the Std_Part of the body they are attached to.

The Fasteners workbench creates each fastener at the root of the document,
only attached (property BaseObject) to an edge or face of a body. Two
consequences:
  * the body's Std_Part is not a complete component: inserting or freezing
    it leaves its fasteners behind, and the visual insertion lists every
    screw as a separate component;
  * Fasteners places the screw from the edge given in the coordinates of
    the body's parent, but applies that placement in the coordinates of the
    screw's own parent (the document): as soon as the Std_Part is moved,
    the screw is off (98.8 mm off in a test where the Part was moved
    100 mm). Inside the same Std_Part as the body it is exactly in place.

For every fastener: its body is found through BaseObject; if the body is in
a Std_Part, the fastener moves into it; otherwise a Std_Part named after
the body is created around the body and its fasteners. The Fasteners BOM
still counts them (it walks every object of the document).

User-facing texts are in English, translated through i18n.tr().
"""

import FreeCAD as App

from .i18n import tr


def is_fastener(o):
    """Object of the Fasteners workbench (FS* proxy with a BaseObject)."""
    try:
        proxy = getattr(o, "Proxy", None)
        return proxy is not None and "BaseObject" in o.PropertiesList and \
            (type(proxy).__name__.startswith("FS") or
             type(proxy).__module__.startswith("Fastener"))
    except Exception:
        return False


def body_of(fastener):
    """Body (or plain solid) the fastener is attached to, or None."""
    try:
        base = fastener.BaseObject[0] if fastener.BaseObject else None
    except Exception:
        base = None
    o = base
    while o is not None:
        if o.isDerivedFrom("PartDesign::Body"):
            return o
        o = o.getParentGeoFeatureGroup()
    return base                         # attached to a Part::Feature directly


def _container(body):
    """Std_Part directly holding `body` (an Assembly is not one: fasteners of
    an assembly component belong to its own file)."""
    p = body.getParentGeoFeatureGroup()
    if p is not None and p.isDerivedFrom("App::Part") \
            and not p.isDerivedFrom("Assembly::AssemblyObject"):
        return p
    return None


def _selected(doc):
    """Fasteners concerned by the selection: selected fasteners, fasteners
    of selected bodies / Parts; None when nothing is selected (whole doc)."""
    if not App.GuiUp:
        return None
    import FreeCADGui as Gui
    sel = [s.Object for s in Gui.Selection.getSelectionEx(doc.Name)]
    if not sel:
        return None
    out = []
    for f in (o for o in doc.Objects if is_fastener(o)):
        b = body_of(f)
        if f in sel or (b is not None and (b in sel or _container(b) in sel)):
            out.append(f)
    return out


def organize(doc=None, fasteners=None):
    """Group fasteners with their body. Returns (moved, new Parts, skipped)."""
    doc = doc or App.ActiveDocument
    if doc is None:
        raise RuntimeError(tr("No active document."))
    if fasteners is None:
        fasteners = _selected(doc)
    if fasteners is None:
        fasteners = [o for o in doc.Objects if is_fastener(o)]
    if not fasteners:
        raise RuntimeError(tr("No fastener of the Fasteners workbench found."))

    moved, created, skipped = [], [], []
    doc.openTransaction(tr("Group fasteners with their body"))
    try:
        for f in fasteners:
            body = body_of(f)
            if body is None:
                skipped.append(f)
                App.Console.PrintWarning(tr("Fasteners: “{name}” is attached to nothing, "
                                            "left in place.").format(name=f.Label) + "\n")
                continue
            if body.getParentGeoFeatureGroup() is not None and _container(body) is None:
                skipped.append(f)
                App.Console.PrintWarning(tr("Fasteners: the body of “{name}” is directly in "
                                            "an assembly, left in place.").format(name=f.Label)
                                         + "\n")
                continue
            part = _container(body)
            if part is None:
                # Body alone at the root: wrap it into a Std_Part of its name
                part = doc.addObject("App::Part", "Part")
                # Labels are unique: "<body> (Part)" reads better than "Base001"
                part.Label = tr("{body} (Part)").format(body=body.Label)
                part.addObject(body)
                created.append(part)
            if f.getParentGeoFeatureGroup() is not part:
                part.addObject(f)
                moved.append(f)
        doc.recompute()
    finally:
        doc.commitTransaction()
    App.Console.PrintMessage(tr("Fasteners: {n} fastener(s) grouped with their body, "
                                "{p} Part(s) created.").format(n=len(moved), p=len(created))
                             + "\n")
    return moved, created, skipped
