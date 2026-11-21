# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - document helpers
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
docs.py (Assembly Companion) - open source files without losing the
assembly.

Opening a document, even hidden, makes it the ACTIVE document of FreeCAD.
The 3D view still shows the assembly, but every Assembly command then looks
at the wrong document: they are greyed out and the assembly cannot be
activated again (only a restart seemed to help). Every source file opened
by the workbench goes through open_source(), which gives the active
document and its 3D view back to the assembly.
"""

import os

import FreeCAD as App


def same_file(a, b):
    try:
        return bool(a and b) and os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def activate(doc):
    """Make `doc` the active document again, in App and in the GUI (its 3D
    view in front)."""
    if doc is None:
        return
    try:
        App.setActiveDocument(doc.Name)
    except Exception:
        pass
    if not App.GuiUp:
        return
    try:
        import FreeCADGui as Gui
        Gui.setActiveDocument(doc.Name)
        gdoc = Gui.getDocument(doc.Name)
        if gdoc.ActiveView is None or not hasattr(gdoc.ActiveView, "getViewer"):
            Gui.activateView("Gui::View3DInventor", False)
    except Exception:
        pass


def open_source(path, keep=None):
    """Document of `path`: the one already open, else opened HIDDEN (no tab).
    The active document is given back to `keep` (default: the active one)."""
    keep = keep if keep is not None else App.ActiveDocument
    for d in App.listDocuments().values():
        if same_file(d.FileName, path):
            return d
    try:
        doc = App.openDocument(path, True)      # hidden
    except TypeError:                           # very old FreeCAD
        doc = App.openDocument(path)
    if keep is not None and keep is not doc:
        activate(keep)
    return doc
