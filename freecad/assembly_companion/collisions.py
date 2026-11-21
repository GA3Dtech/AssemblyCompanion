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


def _dialog(parent, doc, items, found):
    import FreeCADGui as Gui
    from . import selection_sets as ss
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(tr("Check collisions"))
    dlg.resize(760, 380)
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(QtWidgets.QLabel(
        tr("{n} interference(s) between {p} parts. Click a line to select the two "
           "parts; the overlapping volumes are shown in red (object “Collisions”).")
        .format(n=len(found), p=len(items)) if found else
        tr("No interference between the {p} parts.").format(p=len(items))))
    tree = QtWidgets.QTreeWidget()
    tree.setHeaderLabels([tr("Part A"), tr("Part B"), tr("Volume (mm³)")])
    tree.setRootIsDecorated(False)
    for i, j, vol, _c in sorted(found, key=lambda f: -f[2]):
        it = QtWidgets.QTreeWidgetItem([items[i][1], items[j][1], "%.3f" % vol])
        it.setData(0, 256, (items[i][0], items[j][0]))       # 256 = Qt.UserRole
        tree.addTopLevelItem(it)
    for c in range(3):
        tree.resizeColumnToContents(c)

    def select(item, _col=0):
        Gui.Selection.clearSelection()
        for k in item.data(0, 256):
            r, s = ss.split_key(k)
            try:
                Gui.Selection.addSelection(doc.Name, r, s)
            except Exception:
                pass
    tree.itemClicked.connect(select)
    lay.addWidget(tree, 1)
    bb = QtWidgets.QDialogButtonBox()
    rm = bb.addButton(tr("Remove the red volumes"), QtWidgets.QDialogButtonBox.ResetRole)
    bb.addButton(QtWidgets.QDialogButtonBox.Close)
    bb.rejected.connect(dlg.reject)

    def remove():
        if doc.getObject(RESULT_NAME) is not None:
            doc.removeObject(RESULT_NAME)
            doc.recompute()
        rm.setEnabled(False)
    rm.clicked.connect(remove)
    rm.setEnabled(bool(found))
    lay.addWidget(bb)
    dlg.setModal(False)
    dlg.show()
    # keep a reference, the dialog is modeless
    Gui.AssemblyCompanionCollisionsDialog = dlg
