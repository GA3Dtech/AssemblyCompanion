# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - import a STEP file as a part of the assembly
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
step_import.py (Assembly Companion) - "Import STEP as part".

The STEP importer of FreeCAD decomposes the file into an import group
(App::LinkGroup holding solids or Links to solids). That group cannot be
inserted into an assembly as it is: its elements are not shown through an
assembly component. Here the import groups are turned into App::Part
containers (placements kept, nested groups become nested Parts), all under
one Part named after the STEP file, which is then inserted into the
assembly:
  * mode "file" (default): the Part is saved in a new .FCStd next to the
    assembly and linked to it (durable assemblies: the STEP is converted
    once, the assembly links a FreeCAD file);
  * mode "document": the Part is created inside the assembly document and
    becomes a component directly.
The user's STEP import settings are used (ImportGui in the GUI, colours and
decomposition included; Import without the GUI).

User-facing texts are in English, translated through i18n.tr().
"""

import os

import FreeCAD as App

from . import new_part
from . import panel_model
from . import prefs
from .i18n import tr

EXTENSIONS = (".step", ".stp")
MODES = ("file", "document")


def is_step(path):
    return os.path.splitext(path or "")[1].lower() in EXTENSIONS


def part_name(step_path):
    """Name of the Part / file made from a STEP file: its cleaned stem."""
    return new_part.clean(os.path.splitext(os.path.basename(step_path))[0]) or "STEP"


# ----------------------------------------------------------------------
#  Import and conversion of the import groups
# ----------------------------------------------------------------------
def _import_into(doc, path):
    """Objects created in `doc` by the STEP importer."""
    before = set(o.Name for o in doc.Objects)
    if App.GuiUp:
        import ImportGui
        ImportGui.insert(path, doc.Name)
    else:
        import Import
        Import.insert(path, doc.Name)
    return [o for o in doc.Objects if o.Name not in before]


def _show(o):
    try:
        o.Visibility = True
    except Exception:
        pass


def _move_into(doc, parent, o, placement=None):
    """Move the imported object `o` into the App::Part `parent`. An import
    group becomes a nested App::Part (or, with `placement`, its elements go
    straight into `parent`, placed by `placement` * their own placement)."""
    if o.TypeId == "App::LinkGroup":
        elements = list(o.ElementList)
        o.ElementList = []
        if placement is not None:
            target, plc = parent, placement.multiply(o.Placement)
        else:
            target = doc.addObject("App::Part", o.Name + "_Part")
            target.Label = o.Label
            target.Placement = o.Placement
            parent.addObject(target)
            plc = None
        for e in elements:
            if plc is not None and "Placement" in e.PropertiesList:
                e.Placement = plc.multiply(e.Placement)
            _move_into(doc, target, e)
        doc.removeObject(o.Name)
        return
    parent.addObject(o)
    _show(o)


def make_part(doc, objects, label):
    """App::Part `label` holding the imported `objects` (top level ones; the
    solids Links point to stay where the importer put them, hidden). A
    single top import group gives its elements directly to the Part, its
    placement applied to them (the Part is shown through a Link, which
    ignores the Part's own placement)."""
    names = set(o.Name for o in objects)
    tops = [o for o in objects if not any(p.Name in names for p in o.InList)]
    part = doc.addObject("App::Part", "Part")
    part.Label = label
    groups = [o for o in tops if o.TypeId == "App::LinkGroup"]
    for o in tops:
        if o.TypeId == "App::Part" and o is not part and not o.getParentGeoFeatureGroup():
            part.addObject(o)
        elif o.TypeId == "App::LinkGroup":
            _move_into(doc, part, o, App.Placement() if len(groups) == 1 else None)
        elif o.isDerivedFrom("App::GeoFeature") and o.getParentGeoFeatureGroup() is None:
            part.addObject(o)
            _show(o)
    return part


def _count_solids(part):
    try:
        import Part
        return len(Part.getShape(part).Solids)
    except Exception:
        return 0


# ----------------------------------------------------------------------
#  Import as part (file or document), insertion into the assembly
# ----------------------------------------------------------------------
def default_file(asm_doc, step_path, folder=None):
    folder = folder or (os.path.dirname(asm_doc.FileName) if asm_doc.FileName
                        else os.path.dirname(step_path))
    return os.path.join(folder, part_name(step_path) + ".FCStd")


def import_step(asm_doc, step_path, asm=None, mode="file", file_path=None, insert=True):
    """Import `step_path` as a Part and insert it into the assembly `asm`
    of `asm_doc` (see the module docstring). Returns {"mode", "file",
    "part", "document", "inserted", "solids"}."""
    from . import docs
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))
    if not os.path.isfile(step_path):
        raise IOError(tr("File not found: {file}").format(file=step_path))
    label = part_name(step_path)
    if mode == "document":
        asm_doc.openTransaction(tr("Import STEP as part"))
        try:
            objs = _import_into(asm_doc, step_path)
            part = make_part(asm_doc, objs, label)
            if insert and asm is not None:
                asm.addObject(part)
            asm_doc.recompute()
        except Exception:
            asm_doc.abortTransaction()
            raise
        asm_doc.commitTransaction()
        return {"mode": mode, "file": None, "part": part.Name, "document": asm_doc.Name,
                "inserted": part.Name if insert and asm is not None else None,
                "solids": _count_solids(part)}

    file_path = file_path or default_file(asm_doc, step_path)
    if os.path.exists(file_path):
        raise IOError(tr("{file} already exists: choose another name.").format(file=file_path))
    nd = App.newDocument(label.replace("-", "_").replace(".", "_") or "STEP")
    try:
        objs = _import_into(nd, step_path)
        part = make_part(nd, objs, label)
        nd.recompute()
        nd.saveAs(file_path)
        part_name_, solids = part.Name, _count_solids(part)
    finally:
        App.closeDocument(nd.Name)
    result = {"mode": mode, "file": file_path, "part": part_name_, "document": None,
              "inserted": None, "solids": solids}
    # Opened again hidden: the assembly stays the active document (docs.py)
    src = docs.open_source(file_path, keep=asm_doc)
    result["document"] = src.Name
    if insert and asm is not None:
        asm_doc.openTransaction(tr("Import STEP as part"))
        try:
            link = asm_doc.addObject("App::Link", part_name_)
            link.setLink(src.getObject(part_name_))
            link.Label = label
            asm.addObject(link)
            asm_doc.recompute()
        finally:
            asm_doc.commitTransaction()
        result["inserted"] = link.Name
    return result


# ----------------------------------------------------------------------
#  Panel and command
# ----------------------------------------------------------------------
class ImportStepPanel(panel_model.PanelModel):
    """STEP file, mode (new file / this document), file of the new part;
    OK calls api.import_step."""

    width = 620

    def __init__(self, asm_doc, step_path=""):
        super().__init__()
        self.doc = asm_doc
        self.title = tr("Import STEP as part")
        self.hint = tr("The STEP file is imported as one Std_Part (import groups turned into "
                       "Parts, so that every element is visible in the assembly), then "
                       "inserted into the active assembly.")
        P = panel_model.Param
        self.add(P("step", tr("STEP file:"), "path", step_path, mode="open",
                   filter=tr("STEP files (*.step *.stp *.STEP *.STP)")))
        self.add(P("mode", tr("Store the part:"), "choice", prefs.get("StepImportMode"),
                   options=[("file", tr("In a new FreeCAD file next to the assembly "
                                        "(recommended)")),
                            ("document", tr("In the assembly document"))]))
        self.add(P("file", tr("New file:"), "path", "", mode="save",
                   filter=tr("FreeCAD files (*.FCStd)")))
        self.add(P("insert", tr("Insert into the active assembly"), "bool", True))
        self.action(panel_model.Action("import", tr("Import"), primary=True, accept=True))
        self.changed("step")

    def changed(self, name):
        if name == "step" and self.values["step"]:
            self.values["file"] = default_file(self.doc, self.values["step"])
        if self.values["mode"] == "document":
            self.hidden.add("file")
        else:
            self.hidden.discard("file")

    def trigger(self, name):
        from . import api
        if not is_step(self.values["step"]):
            raise RuntimeError(tr("Choose a STEP file (.step, .stp)."))
        prefs.put("StepImportMode", self.values["mode"])
        target = None
        try:
            from . import explorer
            c = explorer._target_container(self.doc)    # active assembly / Std_Part
            target = c.Name if c is not None else None
        except Exception:
            pass
        self.result = api.import_step(self.doc, self.values["step"], assembly=target,
                                      mode=self.values["mode"],
                                      file_path=self.values["file"] or None,
                                      insert=self.values["insert"])


def import_command(step_path=None, doc=None):
    """GUI command (and explorer action): ask the STEP file and options."""
    from . import bridge, docs
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    if not doc.FileName:
        raise RuntimeError(tr("Save the assembly first: the new part file is created "
                              "next to it."))
    model = ImportStepPanel(doc, step_path or "")
    if not bridge.show_panel(model) or not model.result:
        return None
    r = model.result
    App.Console.PrintMessage(tr("STEP imported as part: {solids} solid(s), {where}.").format(
        solids=r["solids"], where=r["file"] or doc.Label) + "\n")
    return r
