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

def _selected_link_names():
    """Names of the Links targeted by the selection; None = whole document."""
    links = _module("freeze").selection_liens()
    return None if links is None else [o.Name for o in links]


def _freeze():
    _module("api").freeze_parts(App.ActiveDocument, _selected_link_names(),
                                mode=_module("prefs").get("FreezeMode"))


def _relink():
    _module("api").relink_parts(App.ActiveDocument, _selected_link_names())


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


def _outdated():
    _module("outdated").show()


def _bom():
    _module("bom").export()


def _replace():
    _module("replace").replace()


def _archive():
    _module("archive").archive()


def _collisions():
    _module("collisions").check()


def _update_binder():
    _module("new_part").update_binder_from_selection()


def _lightweight():
    _module("lightweight").make_command()


def _restore_full():
    _module("lightweight").restore_command()


def _open_source():
    _module("lightweight").open_source_command()


def _reactivate():
    _module("reactivate").reactivate(App.ActiveDocument)


def _align():
    _module("align").show()


def _insert_component():
    _module("explorer").show_insert_dock()


def _import_step():
    _module("step_import").import_command()


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
    "AssemblyCompanion_Outdated": _Command(
        _outdated, "Outdated.svg", tr("Outdated frozen parts"),
        tr("List the frozen parts whose source file was saved after they were frozen, "
           "and refreeze the chosen ones from the saved source file.")),
    "AssemblyCompanion_Bom": _Command(
        _bom, "Bom.svg", tr("Bill of materials (CSV)"),
        tr("Export the parts of the assembly with their quantities to a CSV file, "
           "frozen parts under their original name and source file, linked parts, "
           "fasteners and sub-assemblies included.")),
    "AssemblyCompanion_Archive": _Command(
        _archive, "Archive.svg", tr("Archive the assembly"),
        tr("Put the assembly and every file it needs (linked parts, sub-assemblies, "
           "optionally the sources of frozen parts) into one zip, relative paths "
           "kept so it opens anywhere once extracted.")),
    "AssemblyCompanion_Lightweight": _Command(
        _lightweight, "Lightweight.svg", tr("Make lightweight"),
        tr("For very large assemblies: replace the selected components (or all) by a "
           "light mesh skin plus a skeleton of the elements their joints use. Joints "
           "and solver keep working; the file no longer holds their BREP.")),
    "AssemblyCompanion_RestoreFull": _Command(
        _restore_full, "RestoreFull.svg", tr("Restore full components"),
        tr("Put the selected lightweight components (or all) back to the real parts "
           "of their source file, joints included; frozen ones are frozen again.")),
    "AssemblyCompanion_OpenSource": _Command(
        _open_source, "OpenSource.svg", tr("Open source file"),
        tr("Open the real file of the selected component (lightweight, frozen or "
           "linked) to work on it.")),
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
    "AssemblyCompanion_Replace": _Command(
        _replace, "Replace.svg", tr("Replace component"),
        tr("Point the selected component to an object of another file (e.g. the next "
           "revision, proposed automatically), keeping its place and its joints. "
           "Frozen components are frozen again; other instances can follow.")),
    "AssemblyCompanion_NewPart": _Command(
        _new_part, "NewPart.svg", tr("New part from selection"),
        tr("Create a new part file (PREFIX_001a_Description) whose Body holds a "
           "SubShapeBinder of the selected faces, edges or parts, to model it in "
           "the context of the assembly.")),
    "AssemblyCompanion_UpdateBinder": _Command(
        _update_binder, "UpdateBinder.svg", tr("Update part binder"),
        tr("Replace the content of the SubShapeBinder of an open part (made with "
           "\"New part from selection\") by the faces, edges or parts selected in the "
           "assembly: to add or remove context elements.")),
    "AssemblyCompanion_Reactivate": _Command(
        _reactivate, "Reactivate.svg", tr("Reactivate assembly"),
        tr("Unlock an assembly that can no longer be activated (Assembly commands "
            "greyed out): close a stuck task panel, leave a pending edit, clear "
            "stale active objects, then activate the selected assembly.")),
    "AssemblyCompanion_Collisions": _Command(
        _collisions, "Collisions.svg", tr("Check collisions"),
        tr("Find the parts of the assembly whose solids overlap (fasteners optionally "
           "left out), list them and show the overlapping volumes in red.")),
    "AssemblyCompanion_Align": _Command(
        _align, "Align.svg", tr("Align elements"),
        tr("Place a body by clicking an element on it, then an element on another "
            "body; adjust flip, offset and rotation.")),
    "AssemblyCompanion_InsertComponent": _Command(
        _insert_component, "InsertComponent.svg", tr("Insert component (visual)"),
        tr("Browse your parts folder with thumbnails and insert parts into the "
            "active assembly; source files do not need to be open."),
        needs_document=False),
    "AssemblyCompanion_ImportStep": _Command(
        _import_step, "ImportStep.svg", tr("Import STEP as part"),
        tr("Import a STEP file as one Std_Part (import groups turned into Parts, every "
           "element visible) saved in a new FreeCAD file or in the assembly, and insert "
           "it into the active assembly.")),
    "AssemblyCompanion_Explorer": _Command(
        _explorer, "Explorer.svg", tr("Local parts explorer"),
        tr("Browse a local master folder of FreeCAD files with thumbnails, in a "
            "central tab."), needs_document=False),
    "AssemblyCompanion_SelectionSets": _Command(
        _selection_sets, "SelectionSets.svg", tr("Selection sets"),
        tr("Panel of named selection sets saved in the document: filter, isolate, "
            "combine."), needs_document=False),
}

# Order of the toolbar and the menu: the workflow, from the parts library
# to the finishing tools, one group per theme (separators between groups).
GROUPS = [
    ("Library", ["AssemblyCompanion_Explorer", "AssemblyCompanion_InsertComponent",
                 "AssemblyCompanion_ImportStep"]),
    ("Build", ["AssemblyCompanion_NewPart", "AssemblyCompanion_UpdateBinder",
               "AssemblyCompanion_Duplicate", "AssemblyCompanion_Replace",
               "AssemblyCompanion_SelectionSets"]),
    ("Durable", ["AssemblyCompanion_Freeze", "AssemblyCompanion_Relink",
                 "AssemblyCompanion_Outdated", "AssemblyCompanion_Diagnostic",
                 "AssemblyCompanion_DeleteJoints"]),
    ("Large assemblies", ["AssemblyCompanion_Lightweight", "AssemblyCompanion_RestoreFull",
                          "AssemblyCompanion_OpenSource"]),
    ("Reports", ["AssemblyCompanion_Bom", "AssemblyCompanion_Collisions",
                 "AssemblyCompanion_Archive"]),
    ("Finishing", ["AssemblyCompanion_Fasteners", "AssemblyCompanion_Align",
                   "AssemblyCompanion_Reactivate"]),
]


def _with_separators(extra=None):
    out = []
    for name, cmds in GROUPS:
        if out:
            out.append("Separator")
        out += cmds + (extra or {}).get(name, [])
    return out


TOOLBAR = _with_separators()
# The menu also holds the commands kept out of the toolbar
MENU = _with_separators({"Durable": ["AssemblyCompanion_Repair"]})


def register():
    for name, cmd in COMMANDS.items():
        Gui.addCommand(name, cmd)
