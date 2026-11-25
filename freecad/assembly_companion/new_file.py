# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - new empty part file with the naming panel
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
new_file.py (Assembly Companion) - "New file": a new, empty part file named
like the new parts (PREFIX_NNNr_Description.FCStd, next free number), so
that every file of a project follows the same naming. By default it holds a
Std_Part container with an empty Body inside, both named after the
description (names can be changed, container and Body can be left out).

User-facing texts are in English, translated through i18n.tr().
"""

import os
import re

import FreeCAD as App

from . import new_part
from . import panel_model
from . import prefs
from .i18n import tr


def create_file(path, part_label=None, body_label=None):
    """Create and save the new file `path`: an App::Part `part_label` (None:
    no container) holding a PartDesign Body `body_label` (None: no Body; at
    the root when there is no container). Never overwrites a file. Returns
    (document, part or None, body or None)."""
    if os.path.exists(path):
        raise RuntimeError(tr("“{file}” already exists.").format(file=os.path.basename(path)))
    stem = os.path.splitext(os.path.basename(path))[0]
    doc = App.newDocument(re.sub(r"\W", "_", stem))
    part = body = None
    if part_label:
        part = doc.addObject("App::Part", "Part")
        part.Label = part_label
    if body_label:
        body = doc.addObject("PartDesign::Body", "Body")
        body.Label = body_label
        if part is not None:
            part.addObject(body)
    doc.recompute()
    doc.saveAs(path)
    return doc, part, body


class NewFilePanel(panel_model.PanelModel):
    """Folder + PREFIX_NNNr_Description with a live preview, optional
    container and Body named after the description; OK calls the API."""

    width = 600

    def __init__(self, ref_doc=None):
        super().__init__()
        self.doc = ref_doc
        self.digits = prefs.get("NewPartDigits")
        self.title = tr("New file")
        self.hint = tr("A new empty part file named like the other parts of the project, "
                       "with a container and a Body ready to model.")
        P = panel_model.Param
        self.add(P("folder", tr("Working folder:"), "path",
                   new_part.NewPartPanel._default_folder(ref_doc), mode="dir"))
        self.add(P("prefix", tr("Prefix:"), "text",
                   prefs.get("NewPartLastPrefix") or prefs.get("NewPartPrefix"),
                   placeholder=tr("e.g. AB")))
        self.add(P("number", tr("Number:"), "int", 0, min=0, max=10 ** self.digits - 1,
                   tip=tr("First number not used by this prefix in the working folder")))
        self.add(P("revision", tr("Revision:"), "text", prefs.get("NewPartRevision")))
        self.add(P("description", tr("Description:"), "text", placeholder=tr("e.g. Bracket")))
        self.add(P("preview", tr("File:"), "note"))
        self.add(P("with_part", tr("Std_Part container"), "bool", True, section=tr("Content")))
        self.add(P("part_label", tr("Container name:"), "text", "", section=tr("Content")))
        self.add(P("with_body", tr("Empty Body"), "bool", True, section=tr("Content")))
        self.add(P("body_label", tr("Body name:"), "text", "", section=tr("Content")))
        self.add(P("switch_wb", tr("Switch to the Part Design workbench"), "bool",
                   prefs.get("NewPartSwitchWorkbench"), section=tr("Content")))
        self.action(panel_model.Action(
            "next", tr("Next free"),
            tip=tr("First number not used by this prefix in the working folder")))
        self.action(panel_model.Action("create", tr("Create"), primary=True, accept=True))
        self._auto = ""                 # names follow the description until edited
        self._next_free()
        self.changed("with_part")

    def path(self):
        v = self.values
        return os.path.join(v["folder"].strip(), new_part.file_name(
            v["prefix"], v["number"], self.digits, v["revision"], v["description"]))

    def problem(self):
        if not os.path.isdir(self.values["folder"].strip()):
            return tr("the folder does not exist")
        if os.path.exists(self.path()):
            return tr("already exists")
        return ""

    def _next_free(self):
        self.values["number"] = new_part.next_number(self.values["folder"].strip(),
                                                     self.values["prefix"], self.digits)
        self._update()

    def _update(self):
        why = self.problem()
        self.values["preview"] = os.path.basename(self.path()) + ("  —  " + why if why else "")

    def changed(self, name):
        v = self.values
        if name in ("folder", "prefix"):
            self._next_free()
        elif name == "description":
            auto = new_part.clean(v["description"])
            for key in ("part_label", "body_label"):
                if v[key] in ("", self._auto):
                    v[key] = auto
            self._auto = auto
        for flag, key in (("with_part", "part_label"), ("with_body", "body_label")):
            if v[flag]:
                self.hidden.discard(key)
            else:
                self.hidden.add(key)
        self._update()

    def trigger(self, name):
        from . import api
        if name == "next":
            self._next_free()
            return
        why = self.problem()
        if why:
            raise RuntimeError(os.path.basename(self.path()) + "  —  " + why)
        v = self.values
        fallback = new_part.clean(v["description"]) or os.path.splitext(
            os.path.basename(self.path()))[0]
        prefs.put("NewPartLastDir", v["folder"].strip())
        prefs.put("NewPartLastPrefix", v["prefix"].strip())
        self.result = api.new_file(
            self.path(),
            part=(v["part_label"].strip() or fallback) if v["with_part"] else None,
            body=(v["body_label"].strip() or fallback) if v["with_body"] else None)


def new_file_command(doc=None):
    """GUI command: naming panel, then the new file opened ready to model."""
    import FreeCADGui as Gui
    from . import bridge
    model = NewFilePanel(doc or App.ActiveDocument)
    if not bridge.show_panel(model) or not model.result:
        return None
    r = model.result
    d = App.getDocument(r["document"])
    try:
        view = Gui.getDocument(d.Name).ActiveView
        if r["part"]:
            view.setActiveObject("part", d.getObject(r["part"]))
        if r["body"]:
            view.setActiveObject("pdbody", d.getObject(r["body"]))
    except Exception:
        pass
    if r["body"] and model.values["switch_wb"]:
        try:
            Gui.activateWorkbench("PartDesignWorkbench")
        except Exception:
            pass
    App.Console.PrintMessage(tr("New file: {file}").format(file=r["path"]) + "\n")
    return d
