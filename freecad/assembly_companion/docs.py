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
import sys
import subprocess

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


def has_assembly(doc):
    return doc is not None and any(
        o.isDerivedFrom("Assembly::AssemblyObject") for o in doc.Objects)


def assembly_document():
    """The only open document holding an assembly and shown in a 3D view,
    or None."""
    if not App.GuiUp:
        return None
    import FreeCADGui as Gui
    found = []
    for d in App.listDocuments().values():
        if not has_assembly(d):
            continue
        try:
            if Gui.getDocument(d.Name).mdiViewsOfType("Gui::View3DInventor"):
                found.append(d)
        except Exception:
            pass
    return found[0] if len(found) == 1 else None


def _shown(doc):
    """True when `doc` has a 3D view (not a source file loaded hidden)."""
    try:
        import FreeCADGui as Gui
        return bool(Gui.getDocument(doc.Name).mdiViewsOfType("Gui::View3DInventor"))
    except Exception:
        return False


def working_document():
    """Document to work in: the active one, unless there is none or it is a
    file loaded in the background (no 3D view) while exactly one shown
    document holds an assembly. FreeCAD can be left in that state after a
    document is closed. That assembly document is made active again."""
    doc = App.ActiveDocument
    if doc is not None and (has_assembly(doc) or _shown(doc)):
        return doc
    other = assembly_document()
    if other is not None:
        activate(other)
        return other
    return doc


# ----------------------------------------------------------------------
#  System file manager
# ----------------------------------------------------------------------
# Variables a FreeCAD AppImage (or bundle) sets for ITS OWN Python and Qt:
# inherited by the file manager they break it (Nemo's Python extensions
# fail on PYTHONHOME and the window never opens).
_BUNDLE_VARS = ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "LD_LIBRARY_PATH",
                "LD_PRELOAD", "QT_QPA_PLATFORM", "QT_PLUGIN_PATH",
                "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH",
                "APPDIR", "APPIMAGE", "ARGV0", "OWD", "FONTCONFIG_FILE", "FONTCONFIG_PATH",
                "SSL_CERT_FILE", "GIT_SSL_CAINFO", "GSETTINGS_SCHEMA_DIR",
                "GDK_PIXBUF_MODULE_FILE", "GIO_MODULE_DIR")


def clean_environment(env=None):
    """Copy of the environment without the variables of the FreeCAD bundle."""
    env = dict(os.environ if env is None else env)
    for k in _BUNDLE_VARS:
        env.pop(k, None)
    return env


def open_in_file_manager(path):
    """Show a folder (or file) in the system file manager."""
    if sys.platform.startswith("win"):
        os.startfile(path)
        return True
    cmd = ["open", path] if sys.platform == "darwin" else ["xdg-open", path]
    try:
        subprocess.Popen(cmd, env=clean_environment(), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        try:
            from PySide import QtCore, QtGui
        except ImportError:
            from PySide6 import QtCore, QtGui
        return QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))
