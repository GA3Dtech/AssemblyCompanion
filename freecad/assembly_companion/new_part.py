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
def create_part(path, supports=None, label=None, shape=None):
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


def _dialog_class():
    QtWidgets, QtCore = _qt()

    class NewPartDialog(QtWidgets.QDialog):
        """Working folder + PREFIX_NNNr_Description, with a live preview."""

        def __init__(self, asm_doc, count, parent=None):
            super(NewPartDialog, self).__init__(parent)
            self.setWindowTitle(tr("New part from selection"))
            self.setMinimumWidth(520)
            form = QtWidgets.QFormLayout(self)

            info = QtWidgets.QLabel(tr("A new file is created with a Body holding a "
                                       "SubShapeBinder of the {n} selected element(s).")
                                    .format(n=count))
            info.setWordWrap(True)
            form.addRow(info)

            row = QtWidgets.QHBoxLayout()
            self.folder = QtWidgets.QLineEdit(self._default_folder(asm_doc))
            browse = QtWidgets.QPushButton(tr("Browse…"))
            browse.clicked.connect(self._browse)
            row.addWidget(self.folder, 1)
            row.addWidget(browse)
            form.addRow(tr("Working folder:"), row)

            self.prefix = QtWidgets.QLineEdit(prefs.get("NewPartLastPrefix")
                                              or prefs.get("NewPartPrefix"))
            self.prefix.setPlaceholderText(tr("e.g. AB"))
            form.addRow(tr("Prefix:"), self.prefix)

            row = QtWidgets.QHBoxLayout()
            self.number = QtWidgets.QSpinBox()
            self.number.setRange(0, 10 ** prefs.get("NewPartDigits") - 1)
            self.next_btn = QtWidgets.QPushButton(tr("Next free"))
            self.next_btn.setToolTip(tr("First number not used by this prefix in the "
                                        "working folder"))
            self.next_btn.clicked.connect(self._next_free)
            row.addWidget(self.number)
            row.addWidget(self.next_btn)
            row.addStretch(1)
            form.addRow(tr("Number:"), row)

            self.revision = QtWidgets.QLineEdit(prefs.get("NewPartRevision"))
            self.revision.setMaximumWidth(80)
            form.addRow(tr("Revision:"), self.revision)

            self.description = QtWidgets.QLineEdit()
            self.description.setPlaceholderText(tr("e.g. Bracket"))
            form.addRow(tr("Description:"), self.description)

            self.preview = QtWidgets.QLabel()
            self.preview.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            form.addRow(tr("File:"), self.preview)

            self.mode = QtWidgets.QComboBox()
            self.mode.addItem(tr("Independent copy (recommended)"), "copy")
            self.mode.addItem(tr("Linked to the assembly (follows its changes)"), "linked")
            self.mode.setToolTip(tr(
                "Independent copy: the binder keeps the geometry of the selection as "
                "it is now; the new part does not depend on the assembly and can be "
                "inserted into it.\nLinked: the binder updates when the assembly "
                "changes; the new part cannot be inserted into this assembly "
                "(the files would depend on each other)."))
            i = self.mode.findData(prefs.get("NewPartBinderMode"))
            self.mode.setCurrentIndex(i if i >= 0 else 0)
            form.addRow(tr("Binder:"), self.mode)

            self.insert = QtWidgets.QCheckBox(tr("Insert the new part into the active assembly"))
            self.insert.setChecked(prefs.get("NewPartInsert"))
            form.addRow(self.insert)
            self.mode.currentIndexChanged.connect(self._mode_changed)
            self._mode_changed()
            self.switch_wb = QtWidgets.QCheckBox(tr("Switch to the Part Design workbench"))
            self.switch_wb.setChecked(prefs.get("NewPartSwitchWorkbench"))
            form.addRow(self.switch_wb)

            self.buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            self.buttons.accepted.connect(self.accept)
            self.buttons.rejected.connect(self.reject)
            form.addRow(self.buttons)

            for w in (self.folder, self.prefix, self.revision, self.description):
                w.textChanged.connect(self._update)
            self.number.valueChanged.connect(self._update)
            self.folder.editingFinished.connect(self._next_free)
            self.prefix.editingFinished.connect(self._next_free)
            self._next_free()
            self.description.setFocus()

        def _default_folder(self, asm_doc):
            for d in (prefs.get("NewPartLastDir"), prefs.get("NewPartDir")):
                if d and os.path.isdir(d):
                    return d
            if asm_doc is not None and asm_doc.FileName:
                return os.path.dirname(asm_doc.FileName)
            return os.path.expanduser("~")

        def _browse(self):
            d = QtWidgets.QFileDialog.getExistingDirectory(
                self, tr("Working folder"), self.folder.text())
            if d:
                self.folder.setText(d)
                self._next_free()

        def _next_free(self):
            self.number.setValue(next_number(self.folder.text().strip(),
                                             self.prefix.text(), prefs.get("NewPartDigits")))
            self._update()

        def path(self):
            return os.path.join(self.folder.text().strip(), file_name(
                self.prefix.text(), self.number.value(), prefs.get("NewPartDigits"),
                self.revision.text(), self.description.text()))

        def _update(self):
            path = self.path()
            ok = os.path.isdir(self.folder.text().strip())
            text = os.path.basename(path)
            if not ok:
                text += "  —  " + tr("the folder does not exist")
            elif os.path.exists(path):
                text += "  —  " + tr("already exists")
                ok = False
            self.preview.setText(text)
            self.preview.setStyleSheet("" if ok else "color: #b91c1c;")
            self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(ok)

        def linked(self):
            return self.mode.currentData() == "linked"

        def _mode_changed(self, *_args):
            self.insert.setEnabled(not self.linked())
            if self.linked():
                self.insert.setChecked(False)

        def remember(self):
            prefs.put("NewPartLastDir", self.folder.text().strip())
            prefs.put("NewPartLastPrefix", self.prefix.text().strip())
            prefs.put("NewPartBinderMode", self.mode.currentData())

    return NewPartDialog


# ----------------------------------------------------------------------
#  Entry point
# ----------------------------------------------------------------------
def new_part_from_selection(doc=None, keys=None):
    """Ask for the file name, then create the part. `keys` = [(root, sub)];
    None takes the current selection of the 3D view / tree."""
    import FreeCADGui as Gui
    QtWidgets, _QtCore = _qt()
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
    dlg = _dialog_class()(doc, len(keys), Gui.getMainWindow())
    run = getattr(dlg, "exec", None) or dlg.exec_
    if not run():
        return None
    dlg.remember()
    path = dlg.path()
    label = clean(dlg.description.text()) or None

    if dlg.linked():
        supports = binder_supports(keys)
        new_doc, body, binder = create_part(path, supports=supports, label=label)
        _log(tr("{file} created, binder linked to {n} object(s).").format(
            file=os.path.basename(path), n=len(supports)))
    else:
        shape, failed = copy_shape(keys)
        if shape is None:
            raise RuntimeError(tr("The selected elements could not be read: nothing "
                                  "was created (see the report view)."))
        new_doc, body, binder = create_part(path, label=label, shape=shape)
        _log(tr("{file} created, {n} element(s) copied.").format(
            file=os.path.basename(path), n=len(keys) - failed))
        if dlg.insert.isChecked():
            link, container = insert_into_assembly(doc, body)
            _log(tr("inserted into “{target}”.").format(
                target=container.Label if container is not None else doc.Label))

    # Leave the user in the new part, ready to model
    try:
        Gui.getDocument(new_doc.Name).ActiveView.setActiveObject("pdbody", body)
    except Exception:
        pass
    if dlg.switch_wb.isChecked():
        try:
            Gui.activateWorkbench("PartDesignWorkbench")
        except Exception:
            pass
    return new_doc
