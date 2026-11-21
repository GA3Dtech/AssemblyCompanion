# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - frozen parts whose source file changed
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
outdated.py (Assembly Companion) - list the frozen parts whose source file
was modified after they were frozen, and refreeze the chosen ones.

Each frozen copy stores its source file and the date it was frozen
(properties FigeFichier / FigeFichierRelatif / FigeDate). A copy is out of
date when the source file is newer than that date. Refreezing updates the
copy (or the frozen Std_Part and its copies) in place from the SAVED source
file, then rewrites the joint references going through the Links that use
it (same names, hidden topological names flushed). If the source geometry
changed, some joint references may no longer match: run "Check frozen
assembly" afterwards.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import datetime

import FreeCAD as App

from . import freeze
from .i18n import tr

OUTDATED, UP_TO_DATE, MISSING = "outdated", "ok", "missing"


def _frozen_time(copy):
    try:
        return datetime.datetime.fromisoformat(copy.FigeDate).timestamp()
    except Exception:
        return None


def status(doc):
    """[(copy, source path or None, source mtime or None, state)] for every
    frozen copy / container of `doc` (not the copies inside a container)."""
    out = []
    for c in doc.Objects:
        if not freeze._est_fige(c) or c.getParentGeoFeatureGroup() is not None:
            continue
        path = freeze.chemin_source(c, doc)
        if path is None:
            out.append((c, None, None, MISSING))
            continue
        mtime = os.path.getmtime(path)
        frozen = _frozen_time(c)
        # 2 s of margin: file systems round modification times
        state = OUTDATED if frozen is None or mtime > frozen + 2 else UP_TO_DATE
        out.append((c, path, mtime, state))
    return out


def refreeze(doc, copies):
    """Update `copies` from their source file; returns the refreshed ones."""
    done = []
    doc.openTransaction(tr("Refreeze outdated parts"))
    try:
        for c in copies:
            doc_src, _opened = freeze._ouvrir_source(c, doc)
            src = freeze._objet_source(c, doc_src) if doc_src else None
            if src is None:
                App.Console.PrintWarning(tr("Refreeze: source of “{name}” not found ({file}).")
                                         .format(name=c.Label, file=c.FigeFichier) + "\n")
                continue
            links = [l for l in doc.Objects if freeze._est_lien(l) and l.LinkedObject is c]
            if freeze._est_conteneur_fige(c):
                freeze._creer_ou_rafraichir_conteneur(doc, src)
                for l in links:
                    # Same object names in the refreshed container: keep the
                    # paths, flush the hidden names
                    freeze.appliquer_reecriture(l, chemins={})
            else:
                freeze._creer_ou_rafraichir_copie(doc, src)
                for l in links:
                    freeze.appliquer_reecriture(l)
            done.append(c)
            App.Console.PrintMessage(tr("Refreeze: “{name}” updated from {file}.").format(
                name=c.Label, file=os.path.basename(c.FigeFichier)) + "\n")
        freeze.marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()
    return done


# ----------------------------------------------------------------------
#  Dialog
# ----------------------------------------------------------------------
def _qt():
    try:
        from PySide import QtWidgets, QtCore
    except ImportError:
        from PySide6 import QtWidgets, QtCore
    return QtWidgets, QtCore


def _date(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "—"


def show(doc=None):
    """Report in a dialog, refreeze the checked parts."""
    import FreeCADGui as Gui
    from . import docs
    QtWidgets, QtCore = _qt()
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    rows = status(doc)
    if not rows:
        raise RuntimeError(tr("This document has no frozen parts."))
    n_old = sum(1 for r in rows if r[3] == OUTDATED)
    n_missing = sum(1 for r in rows if r[3] == MISSING)
    App.Console.PrintMessage(tr("Frozen parts: {total}, out of date: {old}, source "
                                "missing: {missing}.").format(
        total=len(rows), old=n_old, missing=n_missing) + "\n")

    dlg = QtWidgets.QDialog(Gui.getMainWindow())
    dlg.setWindowTitle(tr("Frozen parts up to date?"))
    dlg.resize(820, 420)
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(QtWidgets.QLabel(
        tr("{old} frozen part(s) out of date: their source file was saved after they "
           "were frozen. Checked parts are refrozen from the saved source file.")
        .format(old=n_old)))
    tree = QtWidgets.QTreeWidget()
    tree.setHeaderLabels([tr("Part"), tr("State"), tr("Frozen"), tr("Source saved"),
                          tr("Source file")])
    tree.setRootIsDecorated(False)
    items = []
    for c, path, mtime, state in rows:
        label = {OUTDATED: tr("Out of date"), UP_TO_DATE: tr("Up to date"),
                 MISSING: tr("Source missing")}[state]
        frozen = _frozen_time(c)
        it = QtWidgets.QTreeWidgetItem([c.FigeLabel or c.Label, label, _date(frozen),
                                        _date(mtime), path or c.FigeFichier])
        if state == MISSING:
            it.setFlags(it.flags() & ~QtCore.Qt.ItemIsUserCheckable)
        else:
            it.setCheckState(0, QtCore.Qt.Checked if state == OUTDATED
                             else QtCore.Qt.Unchecked)
        tree.addTopLevelItem(it)
        items.append((it, c, state))
    for i in range(5):
        tree.resizeColumnToContents(i)
    lay.addWidget(tree, 1)
    bb = QtWidgets.QDialogButtonBox()
    ok = bb.addButton(tr("Refreeze checked parts"), QtWidgets.QDialogButtonBox.AcceptRole)
    bb.addButton(QtWidgets.QDialogButtonBox.Close)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    ok.setEnabled(any(s != MISSING for _i, _c, s in items))
    run = getattr(dlg, "exec", None) or dlg.exec_
    if not run():
        return []
    chosen = [c for it, c, s in items
              if s != MISSING and it.checkState(0) == QtCore.Qt.Checked]
    if not chosen:
        return []
    done = refreeze(doc, chosen)
    App.Console.PrintMessage(tr("Refreeze: {n} part(s) updated. Run “Check frozen "
                                "assembly” to verify the joints.").format(n=len(done)) + "\n")
    return done
