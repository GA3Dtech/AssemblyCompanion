# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - interference check between the parts of an assembly
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
collisions.py (Assembly Companion) - find the parts of an assembly whose
solids overlap.

The assembly is split into elementary parts (same walk as the selection
sets: through Links, frozen or linked Std_Parts, sub-assemblies; a Body is
one part), each shape taken at its global place. Pairs whose bounding boxes
overlap are intersected (Shape.common); a common volume above the tolerance
is an interference. Faces in contact give no volume and are not reported.

Fasteners are left out by default: a screw modelled at its nominal diameter
in a tapped hole drawn at the tap drill size always "interferes".

The result is listed in a dialog (a click selects the two parts) and shown
as a red compound "Collisions" in the document (replaced at each check,
deleted from the dialog).

User-facing texts are in English, translated through i18n.tr().
"""

import re

import FreeCAD as App

from . import freeze
from . import panel_model
from .i18n import tr

RESULT_NAME = "AC_Collisions"
TOLERANCE = 1e-3                 # mm3: below, numerical noise of contacts
_FASTENER_NAME = re.compile(r"^(Screw|Nut|Washer|Insert|ThreadedRod|Pin|Bolt|Spacer|"
                            r"Standoff|Rivet|PEM|Heatset)", re.IGNORECASE)


def _is_fastener(o):
    """Fastener of the Fasteners workbench, live or frozen."""
    from . import fasteners
    if fasteners.is_fastener(o):
        return True
    name = o.FigeObjet if freeze._est_copie_figee(o) else o.Name
    return bool(_FASTENER_NAME.match(name or ""))


def parts(doc, roots, skip_fasteners=True):
    """[(key, label path, global solid shape)] of the elementary parts."""
    import Part
    from . import selection_sets as ss
    keys = ss.expand(doc, [ss.make_key(r.Name, "") for r in roots
                           if r.Name != RESULT_NAME])
    out = []
    for k in keys:
        objs = ss.path_objects(doc, k)
        if not objs:
            continue
        leaf = objs[-1]
        if leaf.isDerivedFrom("App::Link") and leaf.LinkedObject is not None:
            leaf = leaf.getLinkedObject(True)
        if skip_fasteners and _is_fastener(leaf):
            continue
        root, sub = ss.split_key(k)
        try:
            shape = Part.getShape(doc.getObject(root), sub, needSubElement=True)
        except Exception:
            continue
        if shape.isNull() or not shape.Solids:
            continue
        # Frozen copies under their original name ("traverse", not "Fige_traverse")
        label = " / ".join((o.FigeLabel or o.Label) if freeze._est_fige(o) else o.Label
                           for o in ss.path_ancestors(doc, k)[1:]) or leaf.Label
        out.append((k, label, shape))
    return out


def find(items, progress=None):
    """[(i, j, volume, common shape)] of the overlapping pairs of `items`."""
    boxes = [s.BoundBox for _k, _l, s in items]
    pairs = [(i, j) for i in range(len(items)) for j in range(i + 1, len(items))
             if boxes[i].intersect(boxes[j])]
    found = []
    for n, (i, j) in enumerate(pairs):
        if progress is not None and not progress(n, len(pairs)):
            break
        try:
            common = items[i][2].common(items[j][2])
            vol = common.Volume
        except Exception:
            continue
        if vol > TOLERANCE:
            found.append((i, j, vol, common))
    return found


def _show_result(doc, found):
    """Red compound of the common volumes (previous result replaced)."""
    import Part
    old = doc.getObject(RESULT_NAME)
    if old is not None:
        doc.removeObject(old.Name)
    if not found:
        return None
    obj = doc.addObject("Part::Feature", RESULT_NAME)
    obj.Label = tr("Collisions")
    obj.Shape = Part.makeCompound([c for _i, _j, _v, c in found])
    if App.GuiUp:
        try:
            obj.ViewObject.ShapeAppearance = [App.Material(DiffuseColor=(0.9, 0.05, 0.05))]
            obj.ViewObject.LineColor = (0.6, 0.0, 0.0)
        except Exception:
            try:
                obj.ViewObject.ShapeColor = (0.9, 0.05, 0.05)
            except Exception:
                pass
    return obj


def check(doc=None):
    """Run the check on the active document and show the dialog."""
    import FreeCADGui as Gui
    from . import docs, bom
    try:
        from PySide import QtWidgets, QtCore
    except ImportError:
        from PySide6 import QtWidgets, QtCore
    parent = Gui.getMainWindow()
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    r = QtWidgets.QMessageBox.question(
        parent, tr("Check collisions"),
        tr("Leave the fasteners out? (a screw in a tapped hole drawn at the drill "
           "size always overlaps)"),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes)
    skip = r == QtWidgets.QMessageBox.Yes

    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
    try:
        items = parts(doc, bom.roots_of(doc), skip)
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()
    if len(items) < 2:
        raise RuntimeError(tr("Fewer than two parts to compare."))

    dlg_p = QtWidgets.QProgressDialog(tr("Comparing the parts…"), tr("Stop"), 0, 100, parent)
    dlg_p.setWindowTitle(tr("Check collisions"))
    dlg_p.setWindowModality(QtCore.Qt.WindowModal)
    dlg_p.setMinimumDuration(300)

    def progress(n, total):
        dlg_p.setMaximum(max(total, 1))
        dlg_p.setValue(n)
        QtWidgets.QApplication.processEvents()
        return not dlg_p.wasCanceled()

    found = find(items, progress)
    dlg_p.close()

    doc.openTransaction(tr("Check collisions"))
    try:
        _show_result(doc, found)
        doc.recompute()
    finally:
        doc.commitTransaction()
    App.Console.PrintMessage(tr("Collisions: {n} interference(s) between {p} parts.").format(
        n=len(found), p=len(items)) + "\n")
    for i, j, vol, _c in found:
        App.Console.PrintWarning("  {a}  ×  {b}  :  {v:.3f} mm³\n".format(
            a=items[i][1], b=items[j][1], v=vol))
    _dialog(parent, doc, items, found)
    return found


class CollisionsPanel(panel_model.PanelModel):
    """Result of the check: one row per interference, a click selects the
    two parts; "Remove the red volumes" deletes the result object."""

    width, height = 760, 400

    def __init__(self, doc, items, found):
        super().__init__()
        self.doc = doc
        self.title = tr("Check collisions")
        self.cancel_label = tr("Close")
        self.hint = tr("{n} interference(s) between {p} parts. Click a line to select the "
                       "two parts; the overlapping volumes are shown in red (object "
                       "“Collisions”).").format(n=len(found), p=len(items)) if found else \
            tr("No interference between the {p} parts.").format(p=len(items))
        self.pairs = {}
        rows = []
        for k, (i, j, vol, _c) in enumerate(sorted(found, key=lambda f: -f[2])):
            self.pairs[str(k)] = (items[i][0], items[j][0])
            rows.append({"id": str(k), "cells": [items[i][1], items[j][1], "%.3f" % vol]})
        self.add(panel_model.Param("pairs", kind="list", checkable=False, rows=rows,
                                   columns=[tr("Part A"), tr("Part B"), tr("Volume (mm³)")]))
        if found:
            self.action(panel_model.Action("remove", tr("Remove the red volumes")))

    def row_clicked(self, name, row_id):
        import FreeCADGui as Gui
        from . import selection_sets as ss
        Gui.Selection.clearSelection()
        for k in self.pairs.get(row_id, ()):
            r, sub = ss.split_key(k)
            try:
                Gui.Selection.addSelection(self.doc.Name, r, sub)
            except Exception:
                pass

    def trigger(self, name):
        if self.doc.getObject(RESULT_NAME) is not None:
            self.doc.openTransaction(tr("Remove the red volumes"))
            try:
                self.doc.removeObject(RESULT_NAME)
                self.doc.recompute()
            finally:
                self.doc.commitTransaction()


def _dialog(parent, doc, items, found):
    """Modeless result panel (QML or widgets, see bridge.py)."""
    from . import bridge
    return bridge.show_panel(CollisionsPanel(doc, items, found), parent, modal=False)
