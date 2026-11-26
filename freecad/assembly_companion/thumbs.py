# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - thumbnails of FreeCAD files
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
thumbs.py (Assembly Companion) - thumbnails of the FreeCAD files of the
library, as in PiStock:
  * startup check: FreeCAD writes a thumbnail into each file it saves only
    when "Save thumbnail into project file" is on; the explorer needs it
    (256 px for sharp cards). When it is off or smaller, the user is asked
    once whether to turn it on;
  * "Generate thumbnails": the FreeCAD files of a folder that have no
    thumbnail (or a smaller one) are opened, shown in an isometric view
    fitted to the part (as V, F), saved and closed. Saving rewrites the file
    with THIS FreeCAD version (an older FreeCAD may not open it any more):
    by default the tool works on a copy of the folder.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import shutil

import FreeCAD as App

from . import panel_model
from . import previews
from .i18n import tr

DOC_PARAMS = "User parameter:BaseApp/Preferences/Document"
SIZE = 256


# ----------------------------------------------------------------------
#  Settings and files
# ----------------------------------------------------------------------
def settings_ok():
    g = App.ParamGet(DOC_PARAMS)
    return g.GetBool("SaveThumbnail", False) and g.GetInt("ThumbnailSize", 128) >= SIZE


def enable_settings():
    g = App.ParamGet(DOC_PARAMS)
    g.SetBool("SaveThumbnail", True)
    if g.GetInt("ThumbnailSize", 128) < SIZE:
        g.SetInt("ThumbnailSize", SIZE)


def thumbnail_width(path):
    """Width of the thumbnail stored in a .FCStd, 0 when there is none."""
    return previews.png_size(previews.fcstd_thumbnail(path))[0]


def fcstd_files(folder, recursive=True):
    out = []
    for dirpath, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        out += [os.path.join(dirpath, f) for f in sorted(files) if f.lower().endswith(".fcstd")]
        if not recursive:
            break
    return out


def missing(folder, recursive=True, size=SIZE):
    """FreeCAD files of `folder` whose thumbnail is missing or smaller."""
    return [p for p in fcstd_files(folder, recursive) if thumbnail_width(p) < size]


def copy_folder(folder):
    """Copy of the FreeCAD files of `folder` (sub-folders kept, so links
    between the files still work) into a new folder next to it. Returns its
    path."""
    base = os.path.normpath(folder) + "_thumbnails"
    dest, n = base, 1
    while os.path.exists(dest):
        n += 1
        dest = "%s%d" % (base, n)
    for p in fcstd_files(folder, True):
        target = os.path.join(dest, os.path.relpath(p, folder))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(p, target)
    return dest


# ----------------------------------------------------------------------
#  Generation (GUI: the thumbnail is a capture of the 3D view)
# ----------------------------------------------------------------------
def generate(paths, progress=None):
    """Open, fit, save and close each file. Files already open in FreeCAD
    are skipped (never touch the user's documents). Returns {"done": [...],
    "skipped": [...], "failed": [{"file", "error"}]}."""
    import FreeCADGui as Gui
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    g = App.ParamGet(DOC_PARAMS)
    saved = (g.GetBool("SaveThumbnail", False), g.GetInt("ThumbnailSize", 128))
    g.SetBool("SaveThumbnail", True)
    g.SetInt("ThumbnailSize", max(SIZE, saved[1]))
    active = App.ActiveDocument.Name if App.ActiveDocument else None
    result = {"done": [], "skipped": [], "failed": []}
    open_files = set(os.path.normcase(os.path.abspath(d.FileName))
                     for d in App.listDocuments().values() if d.FileName)
    try:
        for i, path in enumerate(paths):
            if progress is not None and not progress(i, len(paths), path):
                break
            if os.path.normcase(os.path.abspath(path)) in open_files:
                result["skipped"].append(path)
                continue
            before = set(App.listDocuments())
            try:
                doc = App.openDocument(path)
                view = Gui.getDocument(doc.Name).ActiveView
                view.viewIsometric()
                view.fitAll()
                QtWidgets.QApplication.processEvents()
                doc.save()
                result["done"].append(path)
            except Exception as exc:
                result["failed"].append({"file": path, "error": str(exc)})
            finally:
                for n in set(App.listDocuments()) - before:     # with what it loaded
                    try:
                        App.closeDocument(n)
                    except Exception:
                        pass
    finally:
        g.SetBool("SaveThumbnail", saved[0])
        g.SetInt("ThumbnailSize", saved[1])
        if active in App.listDocuments():
            App.setActiveDocument(active)
    return result


# ----------------------------------------------------------------------
#  Startup check
# ----------------------------------------------------------------------
_checked = []


def startup_check(parent=None):
    """Once per session, and only while the setting is wrong: offer to turn
    on the 256 px thumbnails FreeCAD writes when it saves a file."""
    from . import prefs
    if _checked or settings_ok() or prefs.get("ThumbnailCheckDone"):
        return
    _checked.append(True)
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    r = QtWidgets.QMessageBox.question(
        parent, tr("Thumbnails"),
        tr("FreeCAD does not save a 256 px thumbnail into the files (Preferences > General > "
           "Document). The explorer shows each part with it. Turn it on now?\n\nFiles saved "
           "before have no thumbnail: “Generate thumbnails” (accessories) can add them, on a "
           "copy of the folder."),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes)
    if r == QtWidgets.QMessageBox.Yes:
        enable_settings()
    prefs.put("ThumbnailCheckDone", True)


# ----------------------------------------------------------------------
#  Panel and command
# ----------------------------------------------------------------------
class ThumbnailsPanel(panel_model.PanelModel):
    """Folder and options; "Check" counts the files to process, OK runs."""

    width = 620

    def __init__(self, folder=""):
        super().__init__()
        self.title = tr("Generate thumbnails")
        self.hint = tr("Each FreeCAD file without a 256 px thumbnail is opened, shown in an "
                       "isometric view fitted to the part, saved and closed.")
        P = panel_model.Param
        self.add(P("folder", tr("Folder:"), "path", folder, mode="dir"))
        self.add(P("recursive", tr("Include sub-folders"), "bool", True))
        self.add(P("only_missing", tr("Only files without a 256 px thumbnail"), "bool", True))
        self.add(P("mode", tr("Files:"), "choice", "copy",
                   options=[("copy", tr("Work on a copy of the folder (recommended)")),
                            ("inplace", tr("Modify the files in place"))]))
        self.add(P("warning", "", "note", tr(
            "Caution: saving rewrites each file with this FreeCAD version; an older FreeCAD "
            "may no longer open it. Keep a backup, test on a copy first.")))
        self.add(P("confirm", tr("I have a backup: modify the files in place"), "bool", False))
        self.add(P("count", tr("To process:"), "note", tr("click “Check”")))
        self.action(panel_model.Action("check", tr("Check")))
        self.action(panel_model.Action("run", tr("Generate"), primary=True, accept=True))
        self.changed("mode")

    def changed(self, name):
        if self.values["mode"] == "inplace":
            self.hidden.discard("confirm")
        else:
            self.hidden.add("confirm")
        if name in ("folder", "recursive", "only_missing"):
            self.values["count"] = tr("click “Check”")

    def trigger(self, name):
        from . import api
        v = self.values
        folder = v["folder"].strip()
        if not os.path.isdir(folder):
            raise RuntimeError(tr("Folder not found: {path}").format(path=folder))
        if name == "check":
            files = missing(folder, v["recursive"]) if v["only_missing"] else \
                fcstd_files(folder, v["recursive"])
            self.values["count"] = tr("{n} file(s)").format(n=len(files))
            return
        if v["mode"] == "inplace" and not v["confirm"]:
            raise RuntimeError(tr("Check “I have a backup” to modify the files in place, or "
                                  "work on a copy."))
        self.result = api.generate_thumbnails(folder, recursive=v["recursive"],
                                              only_missing=v["only_missing"],
                                              copy=v["mode"] == "copy")


def generate_command():
    from . import bridge, prefs
    model = ThumbnailsPanel(prefs.get("LocalMasterDir"))
    if not bridge.show_panel(model) or not model.result:
        return None
    r = model.result
    App.Console.PrintMessage(tr("Thumbnails: {done} file(s) saved, {skipped} skipped (open), "
                                "{failed} failed, in {folder}").format(
        done=len(r["done"]), skipped=len(r["skipped"]), failed=len(r["failed"]),
        folder=r["folder"]) + "\n")
    for f in r["failed"]:
        App.Console.PrintWarning("  %s: %s\n" % (f["file"], f["error"]))
    return r
