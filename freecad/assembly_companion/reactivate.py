# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - reactivate an assembly that can no longer be activated
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
reactivate.py (Assembly Companion) - put an assembly of the built-in Assembly
workbench back into its active state when double-clicking it no longer works
and every Assembly command stays greyed out.

The built-in workbench enables its commands only when ALL of these hold
(UtilsAssembly.isAssemblyCommandActive):
  * the active view of the document is a 3D view whose active object
    ("assembly" key, else "part") is an assembly;
  * that assembly is really in edit mode (its dragger exists);
  * no task dialog is open.
Double-click only toggles the edit mode, so any stale piece of state locks
the assembly out until FreeCAD restarts. Typical causes:
  * a task dialog left registered (e.g. a joint panel that raised an error);
  * another object of the document still in edit (sketch, body...), which
    makes Gui.Document.setEdit() refuse the assembly silently;
  * a stale active object (sub-assembly, deleted or reloaded object);
  * the active view of the document is not a 3D view (TechDraw page...).
This module clears each of them, reports what it found in the report view,
then enters the edit mode of the assembly the regular way.

User-facing texts are in English, translated through i18n.tr().
"""

import FreeCAD as App

from .i18n import tr

ACTIVE_KEYS = ("assembly", "part")      # 26.x uses "assembly", 1.0 used "part"
ASM_PARAMS = "User parameter:BaseApp/Preferences/Mod/Assembly"


def _is_assembly(o):
    return o is not None and o.isDerivedFrom("Assembly::AssemblyObject")


def _log(msg):
    App.Console.PrintMessage(tr("Reactivate assembly: {msg}").format(msg=msg) + "\n")


# ----------------------------------------------------------------------
#  Which assembly
# ----------------------------------------------------------------------
def _selected_assembly(doc):
    """Deepest assembly of the current selection (the assembly itself, or a
    part / face inside it), or None."""
    import FreeCADGui as Gui
    for sel in Gui.Selection.getSelectionEx(doc.Name, 0):
        top = sel.Object
        for sub in (sel.SubElementNames or ("",)):
            try:
                chain = top.getSubObjectList(sub) if sub else [top]
            except Exception:
                chain = [top]
            asms = [o for o in chain if _is_assembly(o) and o.Document is doc]
            if asms:
                return asms[-1]
            # A part selected in the tree: look at its parents
            parents = [p for p in top.InList if _is_assembly(p)]
            if not sub and parents:
                return parents[0]
    return None


def _target_assembly(doc, view):
    """Selected assembly, else the one recorded as active, else the only
    assembly of the document."""
    asm = _selected_assembly(doc)
    if asm is not None:
        return asm
    for key in ACTIVE_KEYS:
        try:
            o = view.getActiveObject(key)
        except Exception:
            o = None
        if _is_assembly(o) and o.Document is doc:
            return o
    asms = [o for o in doc.Objects if _is_assembly(o)]
    if len(asms) == 1:
        return asms[0]
    if not asms:
        raise RuntimeError(tr("The document “{doc}” contains no assembly.").format(doc=doc.Label))
    raise RuntimeError(tr("The document contains {n} assemblies: select the one to "
                          "reactivate, then run the command again.").format(n=len(asms)))


def _assembly_document():
    """The only open document holding an assembly and shown in a 3D view,
    or None."""
    import FreeCADGui as Gui
    found = []
    for d in App.listDocuments().values():
        if not any(_is_assembly(o) for o in d.Objects):
            continue
        try:
            if Gui.getDocument(d.Name).mdiViewsOfType("Gui::View3DInventor"):
                found.append(d)
        except Exception:
            pass
    return found[0] if len(found) == 1 else None


# ----------------------------------------------------------------------
#  Repair steps
# ----------------------------------------------------------------------
def _ensure_3d_view(gdoc):
    """Make a 3D view of the document the active one; returns it."""
    import FreeCADGui as Gui
    view = gdoc.ActiveView
    if view is not None and hasattr(view, "getActiveObject") \
            and hasattr(view, "getViewer"):
        return view
    if not gdoc.mdiViewsOfType("Gui::View3DInventor"):
        raise RuntimeError(tr("No 3D view is open for this document "
                              "(View → Create new view)."))
    Gui.activateView("Gui::View3DInventor", False)
    view = gdoc.ActiveView
    if view is None or not hasattr(view, "getViewer"):
        raise RuntimeError(tr("Cannot activate the 3D view of the document: click in "
                              "the 3D view, then run the command again."))
    _log(tr("the active view was not a 3D view: 3D view activated again."))
    return view


def _close_task_dialog():
    import FreeCADGui as Gui
    if not Gui.Control.activeDialog():
        return
    Gui.Control.closeDialog()
    if Gui.Control.activeDialog():
        _log(tr("a task panel does not close: close it by hand "
                "(Cancel / Close button of the Tasks tab)."))
    else:
        _log(tr("task panel left open: closed."))


def _reset_edit(gdoc, asm):
    vp = gdoc.getInEdit()
    if vp is None:
        return
    name = vp.Object.Label if getattr(vp, "Object", None) else "?"
    gdoc.resetEdit()
    if vp.Object is not asm:
        _log(tr("“{name}” was still in edit mode: edit mode left.").format(name=name))


def _clear_active_objects(view, asm):
    for key in ACTIVE_KEYS:
        try:
            o = view.getActiveObject(key)
        except Exception:
            continue
        if o is None:
            continue
        stale = o is not asm
        view.setActiveObject(key, None)
        if stale:
            label = getattr(o, "Label", "?")
            _log(tr("stale active object “{name}” (key '{key}'): cleared.").format(
                name=label, key=key))


def _assembly_commands_active(asm):
    """Same test as the built-in workbench, when its module is available."""
    try:
        import UtilsAssembly
        return UtilsAssembly.activeAssembly() is asm \
            and UtilsAssembly.isAssemblyCommandActive()
    except Exception:
        return asm.ViewObject.isInEditMode()


# ----------------------------------------------------------------------
#  Entry point
# ----------------------------------------------------------------------
def reactivate(doc=None):
    """Clear the stale state that blocks the assembly, then activate it.
    Returns True when the Assembly commands are enabled again."""
    import FreeCADGui as Gui
    doc = doc or App.ActiveDocument
    if doc is None or not any(_is_assembly(o) for o in doc.Objects):
        # Typical lock: a source file opened in the background became the
        # active document while the 3D view still shows the assembly
        other = _assembly_document()
        if other is not None:
            if doc is not None:
                _log(tr("the active document was “{doc}”, not the assembly: "
                        "“{asm}” made active again.").format(doc=doc.Label, asm=other.Label))
            doc = other
            from . import docs
            docs.activate(doc)
    if doc is None:
        raise RuntimeError(tr("No active document."))
    gdoc = Gui.getDocument(doc.Name)
    view = _ensure_3d_view(gdoc)
    asm = _target_assembly(doc, view)

    _close_task_dialog()
    _reset_edit(gdoc, asm)
    _clear_active_objects(view, asm)

    # Same as a double-click on the assembly: switch workbench if the user
    # asked for it, then enter edit mode (which sets the active object)
    if App.ParamGet(ASM_PARAMS).GetBool("SwitchToWB", True):
        try:
            Gui.activateWorkbench("AssemblyWorkbench")
        except Exception:
            pass
    Gui.Selection.clearSelection()
    gdoc.setEdit(asm, 0)

    if _assembly_commands_active(asm):
        _log(tr("“{name}” is active again.").format(name=asm.Label))
        return True

    msg = tr("“{name}” could not be reactivated. Save, close and reopen the document: "
             "this rebuilds the display of the assembly without restarting "
             "FreeCAD.").format(name=asm.Label)
    App.Console.PrintWarning(tr("Reactivate assembly: {msg}").format(msg=msg) + "\n")
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), tr("Reactivate assembly"), msg)
    return False
