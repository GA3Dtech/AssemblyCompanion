# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - replace a component by another file, joints kept
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
replace.py (Assembly Companion) - point a component of the assembly to an
object of another file (typically the next revision: AB_001a -> AB_001b),
keeping its place and its joints.

The Link is retargeted and the joint references going through it are
rewritten, like freezing does:
  * linked component: the paths inside the component are kept (same object
    names in the new file, e.g. a revision saved from the previous one);
  * frozen Std_Part: the frozen copy names are translated back to the
    object names of the new file (FigeObjet), then the component is frozen
    again from the new file;
  * frozen Body / solid: element names are kept, then frozen again.
When the new geometry differs (faces renumbered), some joints may need to
be fixed: "Check frozen assembly" tells which.

The file dialog opens on the next revision of the current source file when
one exists (PREFIX_001a_Desc -> PREFIX_001b_*), and the object with the
same internal name is selected by default. Other instances using the same
part can be replaced in the same step.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import re

import FreeCAD as App

from . import docs
from . import freeze
from .i18n import tr

_REVISION = re.compile(r"^(?P<head>.+_\d+)(?P<rev>[A-Za-z]*)(?P<tail>(_.*)?\.FCStd)$",
                       re.IGNORECASE)


def _qt():
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    return QtWidgets


def source_of(link, doc):
    """(source file, object name) of a component, frozen or linked."""
    t = link.LinkedObject
    if freeze._est_fige(t):
        return freeze.chemin_source(t, doc) or t.FigeFichier, t.FigeObjet
    return t.Document.FileName, t.Name


def next_revision(path):
    """Most recent later revision of `path` in its folder
    (AB_001a_X.FCStd -> AB_001c_X.FCStd if a, b, c exist), or None."""
    if not path:
        return None
    m = _REVISION.match(os.path.basename(path))
    if not m:
        return None
    folder = os.path.dirname(path)
    rev = m.group("rev").lower()
    best = None
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    for n in names:
        o = _REVISION.match(n)
        if not o or o.group("head").lower() != m.group("head").lower():
            continue
        r = o.group("rev").lower()
        if (len(r), r) > (len(rev), rev) and (best is None or (len(r), r) > best[0]):
            best = ((len(r), r), os.path.join(folder, n))
    return best[1] if best else None


def _same_part(a, b, doc):
    """True when Links a and b use the same part (same source object)."""
    try:
        return source_of(a, doc) == source_of(b, doc)
    except Exception:
        return False


def replace_link(doc, link, new_obj):
    """Point `link` to `new_obj`, joints kept; frozen stays frozen."""
    old = link.LinkedObject
    frozen = freeze._est_fige(old)
    if freeze._est_conteneur_fige(old):
        freeze.appliquer_reecriture(link, nouvelle_cible=new_obj,
                                    chemins=freeze._chemins_inverses(old, new_obj))
    elif freeze._est_copie_figee(old):
        freeze.appliquer_reecriture(link, nouvelle_cible=new_obj)
    else:
        freeze.appliquer_reecriture(link, nouvelle_cible=new_obj, chemins={})
    return frozen


def replace(doc=None, links=None):
    """Ask for the new file / object and replace the selected component."""
    import FreeCADGui as Gui
    from . import explorer
    QtWidgets = _qt()
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    if links is None:
        links = freeze.selection_liens()
    if not links or len(links) != 1:
        raise RuntimeError(tr("Select ONE component of the assembly (in the tree, or a "
                              "face in the 3D view)."))
    link = links[0]
    old_path, old_name = source_of(link, doc)
    parent = Gui.getMainWindow()

    start = next_revision(old_path) or old_path or os.path.dirname(doc.FileName or "")
    path, _f = QtWidgets.QFileDialog.getOpenFileName(
        parent, tr("Replace “{name}” by…").format(name=link.Label), start,
        "FreeCAD (*.FCStd)")
    if not path:
        return None
    if docs.same_file(path, doc.FileName):
        raise RuntimeError(tr("A file cannot be inserted into itself."))
    src_doc = docs.open_source(path, keep=doc)
    new_obj = explorer.choose_object(src_doc, parent, tr("Replace component"),
                                     os.path.basename(path), preferred=old_name)
    if new_obj is None:
        return None

    others = [l for l in doc.Objects if freeze._est_lien(l) and l is not link
              and l.LinkedObject is not None and _same_part(l, link, doc)]
    targets = [link]
    if others:
        r = QtWidgets.QMessageBox.question(
            parent, tr("Replace component"),
            tr("{n} other instance(s) use the same part ({names}). Replace them "
               "too?").format(n=len(others), names=", ".join(o.Label for o in others[:8])),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes)
        if r == QtWidgets.QMessageBox.Yes:
            targets += others

    to_freeze = []
    doc.openTransaction(tr("Replace component"))
    try:
        for l in targets:
            if replace_link(doc, l, new_obj):
                to_freeze.append(l)
        freeze.marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()
    if to_freeze:
        freeze.figer(doc, to_freeze)
    docs.activate(doc)
    App.Console.PrintMessage(tr("Replace: {n} instance(s) now use {obj} from {file}. Run "
                                "“Check frozen assembly” if joints moved.").format(
        n=len(targets), obj=new_obj.Label, file=os.path.basename(path)) + "\n")
    return targets
