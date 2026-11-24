# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - extract bodies to new files
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
extract.py (Assembly Companion) - "Extract body": start again from a clean
file. Each selected PartDesign Body goes to its own new file (named like the
new parts: PREFIX_NNNr_Description.FCStd) with its WHOLE tree: sketches,
features, datums, and the spreadsheets / variable sets its expressions use.

The new file must stand alone: SubShapeBinders are made detached (they keep
their shape, no link back to the source file), attachments to objects
outside the body are deactivated (the placement is kept). What still points
outside (external geometry of a sketch...) is listed in the report, never
dropped silently. Option: replace the body in the assembly of its document
by a Link to the extracted part, joints kept.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import re

import FreeCAD as App

from . import freeze
from . import new_part
from . import panel_model
from . import prefs
from .i18n import tr

# Helpers a body's expressions may use: copied with it
_HELPERS = ("Spreadsheet::Sheet", "App::VarSet")


# ----------------------------------------------------------------------
#  What goes with a body
# ----------------------------------------------------------------------
def _in_body(o, body):
    return o is body or body.hasObject(o, True) or \
        (body.Origin is not None and (o is body.Origin or o in body.Origin.OriginFeatures))


def tree_of(body):
    """(objects copied with `body`, objects outside it its tree uses): the
    body, its features and origin, and the helpers (spreadsheets, variable
    sets) of the same document its expressions use."""
    inside, outside = [body], []
    for o in body.OutListRecursive:
        if o.Document is body.Document and (_in_body(o, body) or o.TypeId in _HELPERS):
            if o not in inside:
                inside.append(o)
        elif o not in outside and not _in_body(o, body):
            outside.append(o)
    return inside, outside


def names_for(bodies, folder, prefix, digits, revision):
    """File path of the new part of each body, numbers following on."""
    out, number = [], new_part.next_number(folder, prefix, digits)
    for b in bodies:
        while True:
            path = os.path.join(folder, new_part.file_name(prefix, number, digits, revision,
                                                           b.Label))
            number += 1
            if not os.path.exists(path) and path not in out:
                break
        out.append(path)
    return out


# ----------------------------------------------------------------------
#  Extraction
# ----------------------------------------------------------------------
def _external_refs(objects, doc):
    """[(object label, property, target label, target file)] of the link
    properties of `objects` that point outside `doc`."""
    out = []
    for o in objects:
        for p in o.PropertiesList:
            try:
                t = o.getTypeIdOfProperty(p)
            except Exception:
                continue
            if "Link" not in t or p in ("ExpressionEngine",):
                continue
            try:
                v = getattr(o, p)
            except Exception:
                continue
            vals = v if isinstance(v, (list, tuple)) else [v]
            for x in vals:
                base = x[0] if isinstance(x, tuple) and x else x
                if hasattr(base, "Document") and base.Document is not doc:
                    out.append((o.Label, p, base.Label,
                                os.path.basename(base.Document.FileName or base.Document.Name)))
    return out


def _make_standalone(doc):
    """Cut the links of the copied tree to the source file: detached
    binders, deactivated outside attachments. Returns what was done."""
    done = []
    for o in doc.Objects:
        if o.TypeId == "PartDesign::SubShapeBinder" and \
                (getattr(o, "Support", None) or getattr(o, "BindMode", "") != "Detached"):
            o.BindMode = "Detached"     # keeps its shape
            o.Support = None
            done.append(tr("{name}: binder detached").format(name=o.Label))
        if o.TypeId == "PartDesign::SubShapeBinder" and "Context" in o.PropertiesList:
            try:
                o.Context = None        # container the binder was made in (source file)
            except Exception:
                pass
        if "AttachmentSupport" in o.PropertiesList or "Support" in o.PropertiesList:
            prop = "AttachmentSupport" if "AttachmentSupport" in o.PropertiesList else "Support"
            if o.TypeId == "PartDesign::SubShapeBinder":
                continue
            sup = getattr(o, prop, None) or []
            if any(hasattr(b, "Document") and b.Document is not doc for b, _s in sup):
                plc = o.Placement
                setattr(o, prop, None)
                if "MapMode" in o.PropertiesList:
                    o.MapMode = "Deactivated"
                o.Placement = plc
                done.append(tr("{name}: attachment to another file removed, placement "
                               "kept").format(name=o.Label))
    return done


def extract_body(body, path, dry_run=False):
    """Copy `body` and its tree into the new file `path`. Returns a report
    {"body", "file", "copied": [labels], "standalone": [...], "external":
    [...], "volume", "faces"}."""
    inside, outside = tree_of(body)
    report = {"body": body.Name, "file": path, "copied": [o.Label for o in inside],
              "standalone": [], "external": [o.Label for o in outside if o.isDerivedFrom(
                  "App::GeoFeature") or o.TypeId in _HELPERS],
              "volume": round(body.Shape.Volume, 6), "faces": len(body.Shape.Faces)}
    if dry_run:
        return report
    if os.path.exists(path):
        raise RuntimeError(tr("“{file}” already exists.").format(file=os.path.basename(path)))
    stem = os.path.splitext(os.path.basename(path))[0]
    nd = App.newDocument(re.sub(r"\W", "_", stem))
    try:
        nd.saveAs(path)
        nd.copyObject(inside, False)
        report["standalone"] = _make_standalone(nd)
        nd.recompute()
        new_body = [o for o in nd.Objects if o.isDerivedFrom("PartDesign::Body")]
        report["external"] = ["%s.%s -> %s (%s)" % r for r in _external_refs(nd.Objects, nd)]
        report["invalid"] = [o.Label for o in nd.Objects if "Invalid" in o.State]
        if new_body:
            report["new_volume"] = round(new_body[0].Shape.Volume, 6)
            report["new_faces"] = len(new_body[0].Shape.Faces)
            report["new_body"] = new_body[0].Name
        nd.save()
    finally:
        App.closeDocument(nd.Name)
    return report


def replace_in_assembly(doc, body, path, new_body_name):
    """Replace the local `body` of `doc` by a Link to the extracted part,
    at the same place in the same container; joint references are moved
    to the Link, then the original body tree is deleted. Returns the Link
    name, or None when the body is in no container."""
    from . import docs
    parent = body.getParentGeoFeatureGroup()
    src = docs.open_source(path, keep=doc)
    target = src.getObject(new_body_name)
    doc.openTransaction(tr("Replace by the extracted part"))
    try:
        link = doc.addObject("App::Link", body.Name + "_part")
        link.setLink(target)
        link.Label = body.Label
        link.Placement = body.Placement
        if parent is not None:
            parent.addObject(link)
        for o, p, t in list(freeze._proprietes_refs(doc, exclure=(link,))):
            refs = freeze._lire(o, p, t)
            changed = False
            for i, (base, subs) in enumerate(refs):
                if base is body:
                    refs[i] = (link, [freeze.reecrire_sub(s, -1) for s in subs])
                    changed = True
            if changed:
                setattr(o, p, [] if "List" in t else None)
                freeze._ecrire(o, p, t, refs)
        for o in list(body.Group) + [body]:
            if o.Document is doc and doc.getObject(o.Name) is not None:
                doc.removeObject(o.Name)
        doc.recompute()
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    return link.Name


# ----------------------------------------------------------------------
#  Panel and command
# ----------------------------------------------------------------------
def selected_bodies(doc):
    import FreeCADGui as Gui
    out = []
    for s in Gui.Selection.getSelection(doc.Name):
        o = s.getLinkedObject(True) if s.isDerivedFrom("App::Link") else s
        if o.isDerivedFrom("PartDesign::Body") and o.Document is doc and o not in out:
            out.append(o)
    return out


class ExtractPanel(panel_model.PanelModel):
    """Folder, naming and option of the extraction; OK calls the API."""

    width = 620

    def __init__(self, doc, bodies):
        super().__init__()
        self.doc, self.bodies = doc, bodies
        self.title = tr("Extract bodies to new files")
        self.hint = tr("Each body goes to its own new file with its whole tree (sketches, "
                       "features, datums, spreadsheets). Binders are made independent.")
        P = panel_model.Param
        folder = prefs.get("NewPartLastDir") or prefs.get("NewPartDir") or \
            (os.path.dirname(doc.FileName) if doc.FileName else os.path.expanduser("~"))
        self.add(P("folder", tr("Working folder:"), "path", folder, mode="dir"))
        self.add(P("prefix", tr("Prefix:"), "text",
                   prefs.get("NewPartLastPrefix") or prefs.get("NewPartPrefix")))
        self.add(P("revision", tr("Revision:"), "text", prefs.get("NewPartRevision")))
        self.add(P("files", tr("Files:"), "note"))
        self.add(P("replace", tr("Replace the bodies in the assembly by the new parts"), "bool",
                   False))
        self.action(panel_model.Action("extract", tr("Extract"), primary=True, accept=True))
        self.changed("folder")

    def paths(self):
        v = self.values
        return names_for(self.bodies, v["folder"].strip(), v["prefix"], prefs.get(
            "NewPartDigits"), v["revision"])

    def changed(self, name):
        if os.path.isdir(self.values["folder"].strip()):
            self.values["files"] = "\n".join(os.path.basename(p) for p in self.paths())
        else:
            self.values["files"] = tr("the folder does not exist")

    def trigger(self, name):
        from . import api
        v = self.values
        if not os.path.isdir(v["folder"].strip()):
            raise RuntimeError(tr("the folder does not exist"))
        prefs.put("NewPartLastDir", v["folder"].strip())
        prefs.put("NewPartLastPrefix", v["prefix"].strip())
        self.result = api.extract_bodies(self.doc, [b.Name for b in self.bodies],
                                         folder=v["folder"].strip(), prefix=v["prefix"],
                                         revision=v["revision"], replace=v["replace"])


def extract_command(doc=None):
    from . import bridge, docs
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    bodies = selected_bodies(doc)
    if not bodies:
        raise RuntimeError(tr("Select one or more Bodies first."))
    model = ExtractPanel(doc, bodies)
    if not bridge.show_panel(model) or not model.result:
        return None
    for r in model.result["bodies"]:
        App.Console.PrintMessage(tr("Extract: {body} -> {file} ({n} object(s) copied).").format(
            body=r["body"], file=os.path.basename(r["file"]), n=len(r["copied"])) + "\n")
        for line in r["standalone"]:
            App.Console.PrintMessage("  " + line + "\n")
        for line in r["external"]:
            App.Console.PrintWarning("  " + tr("still linked outside: {ref}").format(ref=line)
                                     + "\n")
    return model.result
