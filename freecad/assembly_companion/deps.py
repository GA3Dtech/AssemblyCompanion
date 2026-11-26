# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - check the external dependencies of a document
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
deps.py (Assembly Companion) - "Check dependencies".

When a document is saved, FreeCAD asks "The file contains external
dependencies. Do you want to save the dependent files, too?" as soon as one
of the documents it depends on (Links, binders, expressions to other files,
directly or through another file) is marked modified - often a file opened
in the background (hidden) to read a part, that was recomputed or upgraded.
This tool lists those documents: file, open in a tab or hidden, partially
loaded, modified, what changed in them, and which objects of the document
use them; the modified ones can be saved, or their changes ignored.

User-facing texts are in English, translated through i18n.tr().
"""

import os

import FreeCAD as App

from . import panel_model
from .i18n import tr


def _gui_doc(d):
    if not App.GuiUp:
        return None
    try:
        import FreeCADGui as Gui
        return Gui.getDocument(d.Name)
    except Exception:
        return None


def is_modified(d):
    """Modified flag FreeCAD checks before saving (GUI), else touched objects."""
    g = _gui_doc(d)
    if g is not None:
        return bool(g.Modified)
    return any("Touched" in o.State for o in d.Objects)


def has_view(d):
    g = _gui_doc(d)
    if g is None:
        return False
    try:
        return bool(g.mdiViewsOfType("Gui::View3DInventor"))
    except Exception:
        return False


def _users(doc, dep):
    """Objects of `doc` whose links point into `dep` (directly)."""
    out = []
    for o in doc.Objects:
        try:
            if any(x.Document is dep for x in o.OutList):
                out.append(o)
        except Exception:
            pass
    return out


def dependencies(doc):
    """[{"document", "label", "file", "open_in_tab", "partial", "modified",
    "touched": [labels], "used_by": [object names of doc], "via": label of
    the document that links it when it is an indirect dependency}]."""
    deps = [d for d in doc.getDependentDocuments() if d is not doc]
    out = []
    for d in deps:
        users = _users(doc, d)
        via = ""
        if not users:
            for other in deps:
                if other is not d and _users(other, d):
                    via = other.Label
                    break
        out.append({
            "document": d.Name, "label": d.Label,
            "file": d.FileName or "",
            "open_in_tab": has_view(d),
            "partial": bool(getattr(d, "Partial", False)),
            "modified": is_modified(d),
            "touched": [o.Label for o in d.Objects if "Touched" in o.State][:20],
            "used_by": [o.Name for o in users],
            "via": via})
    out.sort(key=lambda r: (not r["modified"], r["label"].lower()))
    return out


def save_documents(names):
    """Save the documents `names` (internal names). Returns the saved ones."""
    done = []
    for n in names:
        d = App.listDocuments().get(n)
        if d is not None and d.FileName and not getattr(d, "Partial", False):
            d.save()
            done.append(n)
    return done


def ignore_changes(names):
    """Clear the modified flag of the documents `names` (GUI): FreeCAD stops
    asking to save them; their changes in memory are NOT saved."""
    done = []
    for n in names:
        d = App.listDocuments().get(n)
        g = _gui_doc(d) if d is not None else None
        if g is not None:
            g.Modified = False
            done.append(n)
    return done


# ----------------------------------------------------------------------
#  Panel and command
# ----------------------------------------------------------------------
class DependenciesPanel(panel_model.PanelModel):
    """List of the dependencies; checked (modified) ones can be saved or
    their changes ignored. A click on a row selects the objects that use it."""

    width, height = 900, 460

    def __init__(self, doc):
        from . import api
        super().__init__()
        self.doc = doc
        self.title = tr("Check dependencies")
        self.cancel_label = tr("Close")
        self.rows = api.analyze_dependencies(doc)
        n_mod = sum(1 for r in self.rows if r["modified"])
        if not self.rows:
            self.hint = tr("“{doc}” depends on no other file.").format(doc=doc.Label)
        elif n_mod:
            self.hint = tr("{n} file(s) used by “{doc}” are marked modified: that is why FreeCAD "
                           "asks to save the dependent files. Save them, or ignore their changes "
                           "if you did not mean to change them (opened in the background to "
                           "read a part, recomputed...).").format(n=n_mod, doc=doc.Label)
        else:
            self.hint = tr("No file used by “{doc}” is modified: FreeCAD has nothing more to "
                           "save with it.").format(doc=doc.Label)
        rows = []
        for r in self.rows:
            where = tr("tab") if r["open_in_tab"] else tr("hidden")
            if r["partial"]:
                where += ", " + tr("partial")
            used = (tr("via {doc}").format(doc=r["via"]) if r["via"]
                    else str(len(r["used_by"])))
            rows.append({"id": r["document"], "checked": r["modified"],
                         "enabled": r["modified"],
                         "cells": [r["label"], tr("modified") if r["modified"] else "—", where,
                                   used, ", ".join(r["touched"][:4]),
                                   os.path.basename(r["file"])]})
        self.add(panel_model.Param(
            "deps", kind="list", rows=rows,
            columns=[tr("File"), tr("State"), tr("Open"), tr("Used by"), tr("Changed objects"),
                     tr("Path")]))
        if n_mod:
            self.action(panel_model.Action("ignore", tr("Ignore their changes"), accept=True,
                                           tip=tr("FreeCAD stops asking; the changes in memory "
                                                  "are not saved")))
            self.action(panel_model.Action("save", tr("Save checked files"), primary=True,
                                           accept=True))

    def trigger(self, name):
        from . import api
        names = self.get("deps")
        if name == "save":
            self.result = {"saved": api.save_dependencies(self.doc, names)}
        else:
            self.result = {"ignored": api.ignore_dependency_changes(self.doc, names)}


def check_command(doc=None):
    from . import bridge, docs
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    model = DependenciesPanel(doc)
    for r in model.rows:
        App.Console.PrintMessage("  %s  %s  %s\n" % (
            "*" if r["modified"] else " ", r["label"], r["file"]))
    if bridge.show_panel(model) and model.result:
        App.Console.PrintMessage(tr("Dependencies: {result}").format(result=model.result) + "\n")
    return model.result
