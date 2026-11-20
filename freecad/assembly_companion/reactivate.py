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

User-facing messages are in French; code comments are in English.
"""

import FreeCAD as App

ACTIVE_KEYS = ("assembly", "part")      # 26.x uses "assembly", 1.0 used "part"
ASM_PARAMS = "User parameter:BaseApp/Preferences/Mod/Assembly"


def _is_assembly(o):
    return o is not None and o.isDerivedFrom("Assembly::AssemblyObject")


def _log(msg):
    App.Console.PrintMessage("Réactiver l'assemblage : %s\n" % msg)


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
        raise RuntimeError("Le document « %s » ne contient aucun assemblage." % doc.Label)
    raise RuntimeError("Le document contient %d assemblages : sélectionnez celui "
                       "à réactiver, puis relancez la commande." % len(asms))


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
        raise RuntimeError("Aucune vue 3D ouverte pour ce document "
                           "(Affichage → Créer une vue 3D).")
    Gui.activateView("Gui::View3DInventor", False)
    view = gdoc.ActiveView
    if view is None or not hasattr(view, "getViewer"):
        raise RuntimeError("Impossible d'activer la vue 3D du document : "
                           "cliquez dans la vue 3D puis relancez la commande.")
    _log("la vue active n'était pas une vue 3D : vue 3D réactivée.")
    return view


def _close_task_dialog():
    import FreeCADGui as Gui
    if not Gui.Control.activeDialog():
        return
    Gui.Control.closeDialog()
    if Gui.Control.activeDialog():
        _log("un panneau de tâches ne se ferme pas : fermez-le à la main "
             "(bouton Annuler / Fermer de l'onglet Tâches).")
    else:
        _log("panneau de tâches resté ouvert : fermé.")


def _reset_edit(gdoc, asm):
    vp = gdoc.getInEdit()
    if vp is None:
        return
    name = vp.Object.Label if getattr(vp, "Object", None) else "?"
    gdoc.resetEdit()
    if vp.Object is not asm:
        _log("« %s » était encore en édition : édition quittée." % name)


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
            _log("objet actif périmé « %s » (clé '%s') : effacé." % (label, key))


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
    if doc is None:
        raise RuntimeError("Aucun document actif.")
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
        _log("« %s » est de nouveau actif." % asm.Label)
        return True

    msg = ("« %s » n'a pas pu être réactivé. Enregistrez, fermez puis rouvrez le "
           "document : cela recrée l'affichage de l'assemblage sans redémarrer "
           "FreeCAD." % asm.Label)
    App.Console.PrintWarning("Réactiver l'assemblage : %s\n" % msg)
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), "Réactiver l'assemblage", msg)
    return False
