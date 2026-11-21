# SPDX-License-Identifier: LGPL-2.1-or-later
"""
commands.py (Assembly Companion) - FreeCAD commands of the workbench.

Every command imports its tool module lazily, in Activated(), so that
loading FreeCAD and switching workbenches stays fast.
"""

import importlib

import FreeCAD as App
import FreeCADGui as Gui

from . import icon
from .i18n import tr


def _module(name):
    return importlib.import_module("freecad.assembly_companion." + name)


def _has_document():
    return App.ActiveDocument is not None


class _Command:
    """Generic command: runs `action()` and reports errors in the report view
    instead of letting them escape into FreeCAD."""

    def __init__(self, action, icon_file, menu_text, tooltip,
                 needs_document=True, accel=None):
        self._action = action
        self._icon = icon_file
        self._menu_text = menu_text
        self._tooltip = tooltip
        self._needs_document = needs_document
        self._accel = accel

    def GetResources(self):
        res = {"Pixmap": icon(self._icon),
               "MenuText": self._menu_text,
               "ToolTip": self._tooltip}
        if self._accel:
            res["Accel"] = self._accel
        return res

    def Activated(self):
        try:
            self._action()
        except Exception as exc:  # surface the error, never crash FreeCAD
            import traceback
            App.Console.PrintError("Assembly Companion: %s\n%s\n"
                                   % (exc, traceback.format_exc()))

    def IsActive(self):
        return _has_document() if self._needs_document else True


# --------------------------------------------------------------------------
#  Actions
# --------------------------------------------------------------------------

def _freeze():
    m = _module("freeze")
    m.figer(App.ActiveDocument, m.selection_liens())


def _relink():
    m = _module("freeze")
    m.relier(App.ActiveDocument, m.selection_liens())


def _delete_joints():
    m = _module("freeze")
    m.supprimer_liaisons(m.selection_composants())


def _diagnostic():
    _module("freeze").diagnostic(App.ActiveDocument)


def _repair():
    _module("freeze").reparer(App.ActiveDocument)


def _duplicate():
    _module("duplicate").duplicate(App.ActiveDocument)


def _fasteners():
    _module("fasteners").organize(App.ActiveDocument)


def _new_part():
    _module("new_part").new_part_from_selection(App.ActiveDocument)


def _reactivate():
    _module("reactivate").reactivate(App.ActiveDocument)


def _align():
    _module("align").show()


def _insert_component():
    _module("explorer").show_insert_dock()


def _explorer():
    _module("explorer").show_explorer_tab()


def _selection_sets():
    _module("selection_sets").show_panel()


# --------------------------------------------------------------------------
#  Registration
# --------------------------------------------------------------------------

COMMANDS = {
    "AssemblyCompanion_Freeze": _Command(
        _freeze, "Freeze.svg", tr("Freeze parts"),
        tr("Replace linked parts by dead BREP copies stored in the assembly, so it "
            "reopens identically years later. Selected parts, or all if nothing is "
            "selected.")),
    "AssemblyCompanion_Relink": _Command(
        _relink, "Relink.svg", tr("Relink to sources"),
        tr("Point frozen parts back to their source file, to edit them. Selected "
            "parts, or all if nothing is selected.")),
    "AssemblyCompanion_DeleteJoints": _Command(
        _delete_joints, "DeleteJoints.svg", tr("Delete part joints"),
        tr("Delete every joint (and grounding) of the selected parts, after "
            "confirmation.")),
    "AssemblyCompanion_Diagnostic": _Command(
        _diagnostic, "Diagnostic.svg", tr("Check frozen assembly"),
        tr("Check in the report view that every joint reference resolves and that "
            "frozen copies carry no topological history.")),
    "AssemblyCompanion_Repair": _Command(
        _repair, "Repair.svg", tr("Repair frozen copies"),
        tr("Clean frozen copies made by early versions and rewrite their "
            "references.")),
    "AssemblyCompanion_Duplicate": _Command(
        _duplicate, "Duplicate.svg", tr("Duplicate components"),
        tr("Clone the selected components in the assembly: new instances of the "
            "same parts (frozen or not), same place, optionally with their joints. "
            "Source files are not touched.")),
    "AssemblyCompanion_Fasteners": _Command(
        _fasteners, "Fasteners.svg", tr("Group fasteners with their body"),
        tr("Put the screws, nuts, inserts... of the Fasteners workbench into the "
           "Std_Part of the body they are attached to (a Std_Part is created around "
           "a body that has none). The Part becomes a complete component and the "
           "fasteners stay in place when it moves. Selected ones, or all.")),
    "AssemblyCompanion_NewPart": _Command(
        _new_part, "NewPart.svg", tr("New part from selection"),
        tr("Create a new part file (PREFIX_001a_Description) whose Body holds a "
           "SubShapeBinder of the selected faces, edges or parts, to model it in "
           "the context of the assembly.")),
    "AssemblyCompanion_Reactivate": _Command(
        _reactivate, "Reactivate.svg", tr("Reactivate assembly"),
        tr("Unlock an assembly that can no longer be activated (Assembly commands "
            "greyed out): close a stuck task panel, leave a pending edit, clear "
            "stale active objects, then activate the selected assembly.")),
    "AssemblyCompanion_Align": _Command(
        _align, "Align.svg", tr("Align elements"),
        tr("Place a body by clicking an element on it, then an element on another "
            "body; adjust flip, offset and rotation.")),
    "AssemblyCompanion_InsertComponent": _Command(
        _insert_component, "InsertComponent.svg", tr("Insert component (visual)"),
        tr("Browse your parts folder with thumbnails and insert parts into the "
            "active assembly; source files do not need to be open."),
        needs_document=False),
    "AssemblyCompanion_Explorer": _Command(
        _explorer, "Explorer.svg", tr("Local parts explorer"),
        tr("Browse a local master folder of FreeCAD files with thumbnails, in a "
            "central tab."), needs_document=False),
    "AssemblyCompanion_SelectionSets": _Command(
        _selection_sets, "SelectionSets.svg", tr("Selection sets"),
        tr("Panel of named selection sets saved in the document: filter, isolate, "
            "combine."), needs_document=False),
}

TOOLBAR_DURABLE = ["AssemblyCompanion_Freeze", "AssemblyCompanion_Relink",
                   "AssemblyCompanion_DeleteJoints", "AssemblyCompanion_Diagnostic",
                   "AssemblyCompanion_Reactivate"]
TOOLBAR_LIBRARY = ["AssemblyCompanion_InsertComponent", "AssemblyCompanion_Duplicate",
                   "AssemblyCompanion_NewPart", "AssemblyCompanion_Fasteners",
                   "AssemblyCompanion_Explorer",
                   "AssemblyCompanion_Align", "AssemblyCompanion_SelectionSets"]
MENU = (TOOLBAR_DURABLE + ["AssemblyCompanion_Repair", "Separator"]
        + TOOLBAR_LIBRARY)


def register():
    for name, cmd in COMMANDS.items():
        Gui.addCommand(name, cmd)
