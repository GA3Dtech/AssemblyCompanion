# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - new part from a selection (in-context design)
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
new_part.py (Assembly Companion) - create a new part file whose Body holds a
SubShapeBinder of the current selection (parts, faces, edges, vertices of
the assembly), to model a new part in the context of the assembly.

File names follow the pattern  PREFIX_NNNr_Description.FCStd
(e.g. AB_001a_Bracket.FCStd): a free prefix, a zero-padded number, a revision
index and a description. The dialog proposes the next free number of the
prefix in the working folder.

Binder modes:
  * independent copy (default): the selected geometry is computed here, at
    its global place in the assembly (Part.getShape from the top of the
    selection path, Assembly placement included), cleaned through a BREP
    round trip and given to a detached binder (BindMode "Detached", no
    Support). It does not rely on the binder resolving the selection paths,
    which fails for paths holding mapped element names (";#...", given by the
    selection when the assembly is in edit mode). The new file does not
    depend on the assembly, so it can be inserted into it;
  * linked: the binder follows the assembly (BindMode "Synchronized"). The
    two files then depend on each other as soon as the new part is inserted
    into that assembly (FreeCAD: "The graph must be a DAG"), so insertion is
    disabled in this mode.

Avoiding an object cycle in linked mode: the selection paths start at the top of the
assembly (e.g. "Assembly.Link.Body.Face6"). A binder bound to the Assembly
object itself would make the new part depend on the assembly, and the
assembly on the new part as soon as it is inserted: FreeCAD then reports a
cyclic graph. Each support is therefore re-rooted below the containers
(Assembly, Std_Part, groups) at the first Link / Body / solid, whose own
placement still gives the binder the position the part has in the assembly.
The new part can then be inserted into the assembly at the origin and sits
exactly in place.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import re

import FreeCAD as App

from . import panel_model
from . import prefs
from .i18n import tr

_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')


def _log(msg):
    App.Console.PrintMessage(tr("New part: {msg}").format(msg=msg) + "\n")


# ----------------------------------------------------------------------
#  File names
# ----------------------------------------------------------------------
def clean(text):
    """Text usable in a file name (forbidden characters removed)."""
    return _FORBIDDEN.sub("", text or "").strip()


def file_name(prefix, number, digits, revision, description):
    """'AB', 1, 3, 'a', 'Bracket' -> 'AB_001a_Bracket.FCStd'. Empty parts are
    left out with their separator."""
    head = "%0*d%s" % (int(digits), int(number), clean(revision))
    parts = [p for p in (clean(prefix), head, clean(description)) if p]
    return "_".join(parts) + ".FCStd"


def next_number(folder, prefix, digits=3):
    """Next free number for `prefix` in `folder` (1 when none is used)."""
    pat = re.compile(r"^%s_(\d+)" % re.escape(clean(prefix)) if clean(prefix) else r"^(\d+)",
                     re.IGNORECASE)
    used = 0
    try:
        for name in os.listdir(folder):
            m = pat.match(name)
            if m:
                used = max(used, int(m.group(1)))
    except OSError:
        pass
    return used + 1


_PREFIXED = re.compile(r"^([A-Za-z]+)_\d+")


def folder_prefix(folder):
    """Letter prefix of a working folder: the one its part files use
    (AB_001a_..., the most frequent), else the leading letters of the folder
    name (GI_MiniEtau -> GI), else "". The prefix belongs to the folder:
    it never changes from one new file to the next."""
    counts = {}
    try:
        for name in os.listdir(folder):
            m = _PREFIXED.match(name)
            if m and name.lower().endswith(".fcstd"):
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    except OSError:
        pass
    if counts:
        return max(sorted(counts), key=lambda k: counts[k])
    m = re.match(r"^([A-Za-z]{1,6})_", os.path.basename(os.path.normpath(folder or "")))
    return m.group(1) if m else ""


def fit_view_later(doc):
    """Fit the 3D view of `doc` once the GUI has shown it (as V, F)."""
    try:
        from PySide import QtCore
    except ImportError:
        from PySide6 import QtCore
    import FreeCADGui as Gui
    name = doc.Name

    def fit():
        try:
            if name in App.listDocuments():
                view = Gui.getDocument(name).ActiveView
                view.viewIsometric()
                view.fitAll()
        except Exception:
            pass
    QtCore.QTimer.singleShot(200, fit)


def default_prefix(folder):
    return folder_prefix(folder) or prefs.get("NewPartLastPrefix") or prefs.get("NewPartPrefix")


# ----------------------------------------------------------------------
#  Selection -> binder supports
# ----------------------------------------------------------------------
def selection_keys(doc):
    """Current selection of `doc` as (root object, subname) pairs, elements
    (Face6, Edge3...) included."""
    import FreeCADGui as Gui
    out = []
    for so in Gui.Selection.getSelectionEx("", 0):
        if so.DocumentName != doc.Name:
            continue
        for sub in (so.SubElementNames or ("",)):
            if (so.Object, sub) not in out:
                out.append((so.Object, sub))
    return out


def normalize_sub(sub):
    """Selection subname without mapped element names: 'Link.Body.;#7:1;:G0;XTR.Face6'
    -> 'Link.Body.Face6'. Mapped names come from the selection (assembly
    edit mode) and do not resolve once the topology was rebuilt."""
    from .freeze import decouper_sub
    if not sub or ";" not in sub:
        return sub or ""
    objets, _mapped, elem = decouper_sub(sub)
    if not elem and not sub.endswith("."):
        return sub                      # mapped name alone: nothing better
    return ".".join(objets) + "." + elem if objets else elem


def copy_shape(keys):
    """Compound of the selected shapes at their global place in the
    assembly, without topological history. Returns (shape, n_failed)."""
    import Part
    from .freeze import forme_propre
    shapes, failed = [], 0
    for root, sub in keys:
        try:
            sh = Part.getShape(root, normalize_sub(sub), needSubElement=True)
        except Exception:
            sh = None
        if sh is None or sh.isNull():
            failed += 1
            App.Console.PrintWarning(tr("New part: nothing to copy for {path}").format(
                path=root.Label + "." + sub) + "\n")
            continue
        shapes.append(sh)
    if not shapes:
        return None, failed
    return forme_propre(Part.makeCompound(shapes)), failed


def _is_container(o):
    """Assembly / Std_Part / group: objects a support is re-rooted below."""
    if o.TypeId.startswith("App::Link") or o.isDerivedFrom("PartDesign::Body"):
        return False
    return o.isDerivedFrom("App::Part") or o.isDerivedFrom("App::DocumentObjectGroup")


def reroot(root, sub):
    """(object, subname) of a selection re-rooted below its containers, see
    the module docstring. Falls back to (root, sub) when a container has a
    placement (the binder could not keep the position), with a warning."""
    obj, rest = root, sub or ""
    placement = App.Placement()
    while _is_container(obj) and "." in rest:
        name, tail = rest.split(".", 1)
        child = obj.Document.getObject(name)
        if child is None or obj not in child.InList:
            break
        if obj.isDerivedFrom("App::Part"):
            placement = placement.multiply(obj.Placement)
        obj, rest = child, tail
    if obj is root:
        return root, sub
    if not placement.isIdentity():
        App.Console.PrintWarning(tr(
            "New part: “{name}” is moved in the assembly, the binder keeps the "
            "path from the top of the assembly (do not insert the new part into "
            "this assembly: it would create a dependency cycle).").format(name=root.Label)
            + "\n")
        return root, sub
    return obj, rest


def binder_supports(keys):
    """[(object, (subnames...)), ...] for SubShapeBinder.Support."""
    grouped = []
    for root, sub in keys:
        obj, rest = reroot(root, normalize_sub(sub))
        for o, subs in grouped:
            if o is obj:
                if rest not in subs:
                    subs.append(rest)
                break
        else:
            grouped.append((obj, [rest]))
    return [(o, tuple(subs)) for o, subs in grouped]


# ----------------------------------------------------------------------
#  Creation
# ----------------------------------------------------------------------
def create_part(path, supports=None, label=None, shape=None, source=None):
    """Create and save `path` holding a Body with a SubShapeBinder: a
    detached binder holding `shape` (independent copy), or a binder linked
    to `supports`. Returns (document, body, binder)."""
    if os.path.exists(path):
        raise RuntimeError(tr("“{file}” already exists.").format(file=os.path.basename(path)))
    stem = os.path.splitext(os.path.basename(path))[0]
    doc = App.newDocument(re.sub(r"\W", "_", stem))
    # Saved first: the binder links to another file and stores a path
    # relative to this one
    doc.saveAs(path)
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = label or stem
    binder = body.newObject("PartDesign::SubShapeBinder", "Binder")
    binder.Label = tr("Context")
    # Assembly the context comes from, to update the binder later
    binder.addProperty("App::PropertyString", "ContextAssembly", "Assembly Companion",
                       "File of the assembly the context geometry was taken from")
    binder.ContextAssembly = source or ""
    if shape is not None:
        # A detached binder without Support keeps the shape given to it
        binder.BindMode = "Detached"
        binder.Shape = shape
    else:
        binder.Support = supports
    doc.recompute()
    if App.GuiUp:
        try:
            binder.ViewObject.Transparency = 60
        except Exception:
            pass
    doc.save()
    return doc, body, binder


def insert_into_assembly(asm_doc, body):
    """Link to the new Body in the active assembly of `asm_doc`, at the origin
    (the binder already carries the position of the context)."""
    from . import explorer
    container = explorer._target_container(asm_doc)
    asm_doc.openTransaction(tr("Insert new part"))
    try:
        link = asm_doc.addObject("App::Link", body.Name)
        link.setLink(body)
        link.Label = body.Label
        if container is not None:
            # The binder geometry is global: cancel the placement of the
            # assembly (and of its parents) so the part sits exactly in place
            link.Placement = container.getGlobalPlacement().inverse()
        if container is not None:
            container.addObject(link)
        asm_doc.recompute()
    finally:
        asm_doc.commitTransaction()
    return link, container


# ----------------------------------------------------------------------
#  Dialog
# ----------------------------------------------------------------------
def _qt():
    try:
        from PySide import QtWidgets, QtCore
    except ImportError:
        from PySide6 import QtWidgets, QtCore
    return QtWidgets, QtCore


class NewPartPanel(panel_model.PanelModel):
    """Working folder + PREFIX_NNNr_Description with a live preview; OK
    creates the part through api.new_part_from_selection."""

    width = 600

    def __init__(self, asm_doc, keys):
        super().__init__()
        self.doc, self.keys = asm_doc, keys
        self.digits = prefs.get("NewPartDigits")
        self.title = tr("New part from selection")
        self.hint = tr("A new file is created with a Body holding a SubShapeBinder of the "
                       "{n} selected element(s).").format(n=len(keys))
        P = panel_model.Param
        folder = self._default_folder(asm_doc)
        self.add(P("folder", tr("Working folder:"), "path", folder, mode="dir"))
        self.add(P("prefix", tr("Prefix:"), "text", default_prefix(folder),
                   placeholder=tr("e.g. AB"),
                   tip=tr("Letters of the working folder (taken from its part files, or from "
                          "its name)")))
        self.add(P("number", tr("Number:"), "int", 0, min=0, max=10 ** self.digits - 1,
                   tip=tr("First number not used by this prefix in the working folder")))
        self.add(P("revision", tr("Revision:"), "text", prefs.get("NewPartRevision")))
        self.add(P("description", tr("Description:"), "text", placeholder=tr("e.g. Bracket")))
        self.add(P("preview", tr("File:"), "note"))
        mode = prefs.get("NewPartBinderMode")
        self.add(P("mode", tr("Binder:"), "choice", mode if mode in ("copy", "linked") else "copy",
                   options=[("copy", tr("Independent copy (recommended)")),
                            ("linked", tr("Linked to the assembly (follows its changes)"))],
                   tip=tr("Independent copy: the binder keeps the geometry of the selection "
                          "as it is now; the new part does not depend on the assembly and "
                          "can be inserted into it.\nLinked: the binder updates when the "
                          "assembly changes; the new part cannot be inserted into this "
                          "assembly (the files would depend on each other).")))
        self.add(P("insert", tr("Insert the new part into the active assembly"), "bool",
                   prefs.get("NewPartInsert")))
        self.add(P("switch_wb", tr("Switch to the Part Design workbench"), "bool",
                   prefs.get("NewPartSwitchWorkbench")))
        self.action(panel_model.Action(
            "next", tr("Next free"),
            tip=tr("First number not used by this prefix in the working folder")))
        self.action(panel_model.Action("create", tr("Create"), primary=True, accept=True))
        self._next_free()
        self.changed("mode")

    @staticmethod
    def _default_folder(asm_doc):
        for d in (prefs.get("NewPartLastDir"), prefs.get("NewPartDir")):
            if d and os.path.isdir(d):
                return d
        if asm_doc is not None and asm_doc.FileName:
            return os.path.dirname(asm_doc.FileName)
        return os.path.expanduser("~")

    def path(self):
        v = self.values
        return os.path.join(v["folder"].strip(), file_name(
            v["prefix"], v["number"], self.digits, v["revision"], v["description"]))

    def problem(self):
        """Why the file cannot be created, or ""."""
        if not os.path.isdir(self.values["folder"].strip()):
            return tr("the folder does not exist")
        if os.path.exists(self.path()):
            return tr("already exists")
        return ""

    def _next_free(self):
        self.values["number"] = next_number(self.values["folder"].strip(),
                                            self.values["prefix"], self.digits)
        self._update()

    def _update(self):
        text, why = os.path.basename(self.path()), self.problem()
        self.values["preview"] = text + ("  —  " + why if why else "")

    def changed(self, name):
        if name == "folder":
            fp = folder_prefix(self.values["folder"].strip())
            if fp:
                self.values["prefix"] = fp
        if name in ("folder", "prefix"):
            self._next_free()
        elif name == "mode":
            # A linked binder makes the files depend on each other: no insertion
            if self.values["mode"] == "linked":
                self.values["insert"] = False
                self.hidden.add("insert")
            else:
                self.hidden.discard("insert")
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
        prefs.put("NewPartLastDir", v["folder"].strip())
        prefs.put("NewPartLastPrefix", v["prefix"].strip())
        prefs.put("NewPartBinderMode", v["mode"])
        linked = v["mode"] == "linked"
        self.result = api.new_part_from_selection(
            self.doc, [[o.Name, sub] for o, sub in self.keys], self.path(),
            label=clean(v["description"]) or None, linked=linked,
            insert=v["insert"] and not linked)


# ----------------------------------------------------------------------
#  Entry point
# ----------------------------------------------------------------------
def new_part_from_selection(doc=None, keys=None):
    """Ask for the file name (generic panel), then create the part. `keys` =
    [(root, sub)]; None takes the current selection of the 3D view / tree."""
    import FreeCADGui as Gui
    from . import bridge
    doc = doc or App.ActiveDocument
    if doc is None:
        raise RuntimeError(tr("No active document."))
    if not doc.FileName:
        raise RuntimeError(tr("Save the assembly first: the binder of the new part "
                              "refers to it by its file."))
    if keys is None:
        keys = selection_keys(doc)
    if not keys:
        raise RuntimeError(tr("Select parts, faces, edges or vertices first (or pick a "
                              "selection set)."))
    model = NewPartPanel(doc, keys)
    if not bridge.show_panel(model) or not model.result:
        return None
    res = model.result
    new_doc = App.getDocument(res["document"])
    body = new_doc.getObject(res["body"])
    if model.values["mode"] == "linked":
        _log(tr("{file} created, binder linked to the selection.").format(
            file=os.path.basename(res["path"])))
    else:
        _log(tr("{file} created, {n} element(s) copied.").format(
            file=os.path.basename(res["path"]), n=len(keys)))
    if res["inserted"]:
        link = doc.getObject(res["inserted"])
        parent = link.getParentGeoFeatureGroup() if link is not None else None
        _log(tr("inserted into “{target}”.").format(
            target=parent.Label if parent is not None else doc.Label))

    # Leave the user in the new part, ready to model, the binder in view
    try:
        Gui.getDocument(new_doc.Name).ActiveView.setActiveObject("pdbody", body)
    except Exception:
        pass
    fit_view_later(new_doc)
    if model.values["switch_wb"]:
        try:
            Gui.activateWorkbench("PartDesignWorkbench")
        except Exception:
            pass
    return new_doc


# ----------------------------------------------------------------------
#  Update the binder of a part from a new selection
# ----------------------------------------------------------------------
def context_binders(asm_doc):
    """SubShapeBinders of the other open documents, the ones made from
    `asm_doc` (property ContextAssembly) first."""
    from . import docs
    mine, others = [], []
    for d in App.listDocuments().values():
        if d is asm_doc:
            continue
        for o in d.Objects:
            if o.TypeId != "PartDesign::SubShapeBinder":
                continue
            src = getattr(o, "ContextAssembly", "") if "ContextAssembly" in o.PropertiesList else ""
            (mine if src and docs.same_file(src, asm_doc.FileName) else others).append(o)
    return mine + others


def update_binder(binder, keys):
    """Replace the content of `binder` by the selected elements: a new copy
    for a detached binder, new supports for a linked one."""
    doc = binder.Document
    doc.openTransaction(tr("Update binder"))
    try:
        if binder.BindMode == "Detached" or not binder.Support:
            shape, failed = copy_shape(keys)
            if shape is None:
                raise RuntimeError(tr("The selected elements could not be read: nothing "
                                      "was changed (see the report view)."))
            binder.Shape = shape
        else:
            binder.Support = binder_supports(keys)
        doc.recompute()
    finally:
        doc.commitTransaction()


def update_binder_from_selection(doc=None):
    """Select the new context in the assembly, then pick the binder to update
    (a part made with "New part from selection", open in FreeCAD)."""
    import FreeCADGui as Gui
    from . import docs
    QtWidgets, _QtCore = _qt()
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    keys = selection_keys(doc)
    if not keys:
        raise RuntimeError(tr("Select in the assembly the faces, edges or parts the binder "
                              "must hold, then run the command again."))
    binders = context_binders(doc)
    if not binders:
        raise RuntimeError(tr("No SubShapeBinder in the other open documents: open the "
                              "part to update first."))
    labels = ["%s  —  %s" % (b.Document.Label, b.Label) for b in binders]
    choice, ok = QtWidgets.QInputDialog.getItem(
        Gui.getMainWindow(), tr("Update binder"),
        tr("Binder to fill with the {n} selected element(s):").format(n=len(keys)),
        labels, 0, False)
    if not ok:
        return None
    binder = binders[labels.index(choice)]
    update_binder(binder, keys)
    _log(tr("“{binder}” of {file} updated with {n} element(s). Save that file to keep "
            "it.").format(binder=binder.Label, file=binder.Document.Label, n=len(keys)))
    return binder
