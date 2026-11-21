# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - archive an assembly with every file it needs
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
archive.py (Assembly Companion) - "pack and go": put an assembly and every
file it needs into one zip, to hand a project over or archive it.

Files collected:
  * the assembly itself;
  * every document it still depends on through Links, recursively
    (Document.getDependentDocuments: sub-assemblies, linked parts);
  * optionally the source files of the frozen parts (not needed to open the
    assembly, but needed to modify a part later).

Paths are stored relative to the deepest folder common to all the files, so
the relative paths FreeCAD stores in Links (and the FigeFichierRelatif of
frozen copies) still resolve once the zip is extracted anywhere. A file on
another drive (Windows) goes to "_external/". The files are copied as SAVED
on disk: unsaved changes are reported first. A MANIFEST.txt lists the
content, the FreeCAD version and the date.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import datetime
import zipfile

import FreeCAD as App

from . import freeze
from .i18n import tr


def collect(doc, with_sources=True):
    """(files, missing): absolute paths of the files the assembly needs, and
    the paths of frozen part sources that cannot be found."""
    files, missing = [], []

    def add(path):
        if path and os.path.isfile(path):
            p = os.path.normpath(os.path.abspath(path))
            if p not in files:
                files.append(p)
            return True
        return False

    add(doc.FileName)
    try:
        deps = doc.getDependentDocuments()
    except Exception:
        deps = []
    for d in deps:
        add(d.FileName)
    if with_sources:
        for d in [doc] + list(deps):
            for c in d.Objects:
                if freeze._est_fige(c) and c.getParentGeoFeatureGroup() is None:
                    src = freeze.chemin_source(c, d)
                    if not add(src) and c.FigeFichier not in missing:
                        missing.append(c.FigeFichier)
    return files, missing


def unsaved(doc):
    """Documents of the archive with unsaved changes."""
    try:
        deps = doc.getDependentDocuments()
    except Exception:
        deps = [doc]
    out = []
    for d in deps:
        try:
            if App.GuiUp:
                import FreeCADGui as Gui
                modified = Gui.getDocument(d.Name).Modified
            else:
                modified = any(o.isTouched() for o in d.Objects)
            if modified:
                out.append(d)
        except Exception:
            pass
    return out


def arcnames(files):
    """{absolute path: name in the zip}, relative to the common folder."""
    try:
        root = os.path.commonpath([os.path.dirname(f) for f in files])
    except ValueError:              # different drives
        root = os.path.dirname(files[0])
    out = {}
    for f in files:
        try:
            rel = os.path.relpath(f, root)
        except ValueError:
            rel = None
        if rel is None or rel.startswith(".."):
            rel = os.path.join("_external", os.path.basename(f))
        out[f] = rel.replace(os.sep, "/")
    return out


def write_zip(zip_path, doc, files, missing):
    names = arcnames(files)
    lines = [tr("Archive of {file}").format(file=os.path.basename(doc.FileName)),
             tr("Created {date} with FreeCAD {version}").format(
                 date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                 version=".".join(App.Version()[:3])),
             ""]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, names[f])
            lines.append(names[f])
        if missing:
            lines += ["", tr("Frozen part sources not found:")] + missing
        z.writestr("MANIFEST.txt", "\n".join(lines) + "\n")
    return names


def archive(doc=None):
    """Ask for the zip file and write the archive of the active document."""
    import FreeCADGui as Gui
    from . import docs
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    parent = Gui.getMainWindow()
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    if not doc.FileName:
        raise RuntimeError(tr("Save the document first."))
    changed = unsaved(doc)
    if changed:
        r = QtWidgets.QMessageBox.question(
            parent, tr("Archive the assembly"),
            tr("These documents have unsaved changes, the archive will hold the "
               "version saved on disk: {names}\n\nContinue?").format(
                names=", ".join(d.Label for d in changed)),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if r != QtWidgets.QMessageBox.Yes:
            return None
    has_frozen = any(freeze._est_fige(o) for o in doc.Objects)
    with_sources = True
    if has_frozen:
        r = QtWidgets.QMessageBox.question(
            parent, tr("Archive the assembly"),
            tr("Also include the source files of the frozen parts? They are not needed "
               "to open the assembly, only to modify those parts later."),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes)
        with_sources = r == QtWidgets.QMessageBox.Yes
    files, missing = collect(doc, with_sources)
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    default = os.path.splitext(doc.FileName)[0] + "_archive_" + stamp + ".zip"
    path, _f = QtWidgets.QFileDialog.getSaveFileName(
        parent, tr("Archive the assembly"), default, tr("Zip archives (*.zip)"))
    if not path:
        return None
    if not path.lower().endswith(".zip"):
        path += ".zip"
    write_zip(path, doc, files, missing)
    App.Console.PrintMessage(tr("Archive: {n} file(s) written to {file}").format(
        n=len(files), file=path) + "\n")
    if missing:
        App.Console.PrintWarning(tr("Archive: frozen part sources not found: {names}")
                                 .format(names=", ".join(missing)) + "\n")
    return path
