# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - public API
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
api.py (Assembly Companion) - the stable public API, for scripts, agents and
the FreeCAD MCP server (execute_code / execute_code_headless).

Contract:
  * headless-safe: no dialog, no use of the active view or of
    Gui.ActiveDocument (except reactivate_assembly, which is a GUI matter);
  * the document is passed explicitly (object, internal name or label),
    objects by internal name, files by path;
  * every function returns plain data that json.dumps accepts;
  * errors are the typed exceptions of errors.py;
  * functions that change the document accept dry_run=True (report what
    would be done, change nothing);
  * names stored in documents are never renamed (Fige* properties, groups).

    from freecad.assembly_companion import api
    api.describe()                       # catalogue of the functions
    api.freeze_parts("Assembly")         # -> {"frozen": [...], ...}

API_VERSION is incremented at every breaking change of this module.
"""

import inspect
import os

import FreeCAD as App

from .errors import (AssemblyCompanionError, NoAssemblyError, NoDocumentError,
                     ObjectNotFoundError, SourceNotFoundError, UnsupportedObjectError,
                     GuiRequiredError)
from .i18n import tr

API_VERSION = 1

__all__ = [
    "API_VERSION", "describe", "list_components", "freeze_parts", "relink_parts",
    "delete_part_joints", "diagnose", "outdated_parts", "refreeze_outdated", "bom",
    "export_bom_csv", "check_collisions", "archive", "replace_component",
    "duplicate_components", "make_lightweight", "restore_full", "new_part_from_selection",
    "selection_sets", "create_selection_set", "selection_set_members",
    "combine_selection_sets", "group_fasteners", "reactivate_assembly",
    "AssemblyCompanionError",
]


# ----------------------------------------------------------------------
#  Helpers
# ----------------------------------------------------------------------
def _doc(doc):
    """Document object from an object, an internal name or a label."""
    if doc is None:
        raise NoDocumentError(tr("No active document."))
    if not isinstance(doc, str):
        return doc
    docs = App.listDocuments()
    if doc in docs:
        return docs[doc]
    for d in docs.values():
        if d.Label == doc:
            return d
    raise NoDocumentError(tr("No open document named “{name}”.").format(name=doc), name=doc)


def _obj(doc, name):
    o = doc.getObject(name)
    if o is None:
        raise ObjectNotFoundError(tr("No object “{name}” in {doc}.").format(
            name=name, doc=doc.Label), name=name, document=doc.Name)
    return o


def _objs(doc, names):
    return None if names is None else [_obj(doc, n) for n in names]


def _assemblies(doc):
    from . import bom
    return [o for o in bom.roots_of(doc) if o.isDerivedFrom("Assembly::AssemblyObject")]


def _state(target, doc):
    from . import freeze, lightweight
    if target is None:
        return "broken"
    if lightweight.is_lightweight(target):
        return "lightweight"
    if freeze._est_fige(target):
        return "frozen"
    return "linked" if target.Document is not doc else "local"


def _component_dict(o, doc):
    from . import freeze, lightweight
    t = o.LinkedObject if o.isDerivedFrom("App::Link") else o
    state = _state(t, doc)
    if state == "lightweight":
        src = t.LWFile
    elif state == "frozen":
        src = freeze.chemin_source(t, doc) or t.FigeFichier
    elif t is not None:
        src = t.Document.FileName
    else:
        src = ""
    return {"name": o.Name, "label": o.Label, "type": o.TypeId, "state": state,
            "target": t.Name if t is not None else None,
            "source_file": src or "", "is_lightweight": state == "lightweight",
            "joints": [j.Name for j in freeze.liaisons_de(o)] if o.isDerivedFrom("App::Link")
            else [], "lightweight_module": lightweight.GROUP if state == "lightweight" else ""}


# ----------------------------------------------------------------------
#  Catalogue
# ----------------------------------------------------------------------
def describe():
    """Catalogue of the public functions: name, docstring, parameters with
    their defaults, for an agent to discover the API on its own."""
    out = {"api_version": API_VERSION, "functions": []}
    for name in __all__:
        f = globals().get(name)
        if not inspect.isfunction(f):
            continue
        params = []
        for p in inspect.signature(f).parameters.values():
            d = None if p.default is inspect.Parameter.empty else p.default
            params.append({"name": p.name,
                           "required": p.default is inspect.Parameter.empty,
                           "default": d if isinstance(d, (str, int, float, bool, type(None)))
                           else repr(d)})
        out["functions"].append({"name": name, "doc": inspect.getdoc(f) or "",
                                 "parameters": params})
    return out


# ----------------------------------------------------------------------
#  Components and freezing
# ----------------------------------------------------------------------
def list_components(doc):
    """Components of the assemblies of `doc` (Links and parts directly in an
    assembly): name, label, state (frozen / linked / local / lightweight /
    broken), source file, joints using them."""
    from . import bom
    doc = _doc(doc)
    asms = _assemblies(doc)
    if not asms:
        raise NoAssemblyError(tr("The document “{doc}” contains no assembly.").format(
            doc=doc.Label), document=doc.Name)
    out = []
    for asm in asms:
        for c in bom._children(asm):
            if c.isDerivedFrom("App::Link") or c.isDerivedFrom("Part::Feature") or \
                    c.isDerivedFrom("App::Part"):
                d = _component_dict(c, doc)
                d["assembly"] = asm.Name
                out.append(d)
    return out


def freeze_parts(doc, names=None, dry_run=False):
    """Freeze the Links `names` (internal names; None = every external Link):
    each one points to a dead BREP copy stored in the document.
    -> {"frozen": [...], "skipped": [{"name", "reason"}], "refs_updated": n}"""
    from . import freeze
    doc = _doc(doc)
    links = freeze.liens_externes(doc, _objs(doc, names))
    if dry_run:
        return {"frozen": [l.Name for l in links], "skipped": [], "refs_updated": 0,
                "dry_run": True}
    return freeze.figer(doc, _objs(doc, names))


def relink_parts(doc, names=None, dry_run=False):
    """Point frozen Links back to their source file (None = all of them).
    -> {"relinked": [...], "missing_source": [{"name", "file"}]}"""
    from . import freeze
    doc = _doc(doc)
    links = freeze.liens_figes(doc, _objs(doc, names))
    if dry_run:
        return {"relinked": [l.Name for l in links], "missing_source": [], "dry_run": True}
    return freeze.relier(doc, _objs(doc, names))


def delete_part_joints(doc, names, dry_run=False):
    """Delete every joint and grounding of the components `names`.
    -> {"deleted": [joint names]}"""
    from . import freeze
    doc = _doc(doc)
    comps = _objs(doc, names)
    joints = []
    for c in comps:
        for j in freeze.liaisons_de(c):
            if j.Name not in joints:
                joints.append(j.Name)
    if not dry_run:
        freeze.supprimer_liaisons(comps, confirmer=False)
    return {"deleted": joints, "dry_run": bool(dry_run)}


def diagnose(doc):
    """Check every joint reference and the frozen copies, without changing
    the document. -> {"references": [...], "broken": n, "ok": n,
    "copies": [{"name", "topo_history"}], "unused_copies": [...]}"""
    from . import freeze
    doc = _doc(doc)
    rows = freeze.diagnostic_rows(doc)
    copies = []
    for c in doc.Objects:
        if freeze._est_copie_figee(c):
            try:
                size = int(c.Shape.ElementMapSize)
            except Exception:
                size = -1
            copies.append({"name": c.Name, "label": c.Label, "topo_history": size})
    return {"references": rows, "ok": sum(1 for r in rows if r["ok"]),
            "broken": sum(1 for r in rows if not r["ok"]), "copies": copies,
            "unused_copies": [c.Name for c in freeze.copies_inutilisees(doc)]}


def outdated_parts(doc):
    """Frozen parts and the state of their source file.
    -> [{"name", "label", "state": "outdated"|"ok"|"missing", "source_file",
    "frozen", "source_saved"}]"""
    import datetime
    from . import outdated
    doc = _doc(doc)
    out = []
    for c, path, mtime, state in outdated.status(doc):
        out.append({"name": c.Name, "label": c.FigeLabel or c.Label, "state": state,
                    "source_file": path or c.FigeFichier, "frozen": c.FigeDate,
                    "source_saved": datetime.datetime.fromtimestamp(mtime).isoformat(
                        timespec="seconds") if mtime else None})
    return out


def refreeze_outdated(doc, names=None, dry_run=False):
    """Refreeze the frozen copies `names` (None = every outdated one) from
    their saved source file. -> {"refrozen": [...]}"""
    from . import outdated
    doc = _doc(doc)
    rows = outdated.status(doc)
    if names is None:
        copies = [c for c, _p, _m, s in rows if s == outdated.OUTDATED]
    else:
        copies = [_obj(doc, n) for n in names]
    if dry_run:
        return {"refrozen": [c.Name for c in copies], "dry_run": True}
    return {"refrozen": [c.Name for c in outdated.refreeze(doc, copies)]}


# ----------------------------------------------------------------------
#  BOM, collisions, archive
# ----------------------------------------------------------------------
def bom(doc):
    """Bill of materials of `doc`, frozen parts under their original name.
    -> [{"quantity", "part", "source_file", "state"}] sorted by part"""
    from . import bom as _bom
    doc = _doc(doc)
    rows = _bom.collect(_bom.roots_of(doc), doc)
    return [{"quantity": q, "part": n, "source_file": f, "state": s}
            for (n, f, s), q in sorted(rows.items(), key=lambda kv: (kv[0][0].lower(),
                                                                    kv[0][1]))]


def export_bom_csv(doc, path):
    """Write the bill of materials of `doc` to the CSV file `path`.
    -> {"path", "rows"}"""
    from . import bom as _bom
    doc = _doc(doc)
    rows = _bom.collect(_bom.roots_of(doc), doc)
    _bom.write_csv(path, rows)
    return {"path": path, "rows": len(rows)}


def check_collisions(doc, skip_fasteners=True, show=False):
    """Pairs of parts whose solids overlap. `show` adds the red "Collisions"
    object to the document. -> {"parts": n, "pairs": [{"a", "b", "volume"}]}"""
    from . import bom as _bom, collisions
    doc = _doc(doc)
    items = collisions.parts(doc, _bom.roots_of(doc), skip_fasteners)
    found = collisions.find(items)
    if show:
        doc.openTransaction(tr("Check collisions"))
        try:
            collisions._show_result(doc, found)
            doc.recompute()
        finally:
            doc.commitTransaction()
    return {"parts": len(items),
            "pairs": [{"a": items[i][1], "b": items[j][1], "a_key": items[i][0],
                       "b_key": items[j][0], "volume": round(v, 6)}
                      for i, j, v, _c in found]}


def archive(doc, path, include_frozen_sources=False):
    """Zip `doc` with every file it needs (and optionally the source files of
    its frozen parts). -> {"path", "files": [names in the zip], "missing": [...]}"""
    from . import archive as _archive
    doc = _doc(doc)
    if not doc.FileName:
        raise NoDocumentError(tr("Save the document first."), document=doc.Name)
    files, missing = _archive.collect(doc, include_frozen_sources)
    names = _archive.write_zip(path, doc, files, missing)
    return {"path": path, "files": sorted(names.values()), "missing": missing}


# ----------------------------------------------------------------------
#  Replace, duplicate, lightweight
# ----------------------------------------------------------------------
def replace_component(doc, name, path, object_name=None, all_instances=False, dry_run=False):
    """Point the component `name` (and with all_instances the other Links using
    the same part) to `object_name` of the file `path` (default: the same
    internal name as now), joints kept; frozen components are frozen again.
    -> {"replaced": [...], "refrozen": [...], "object": name, "file": path}"""
    from . import docs, freeze, replace
    doc = _doc(doc)
    link = _obj(doc, name)
    if not freeze._est_lien(link) or link.LinkedObject is None:
        raise UnsupportedObjectError(tr("Select a component of the assembly."), name=name)
    if not os.path.isfile(path):
        raise SourceNotFoundError(tr("Source file not found: {file}").format(file=path),
                                  file=path)
    old_name = replace.source_of(link, doc)[1]
    targets = [link]
    if all_instances:
        targets += [l for l in doc.Objects if freeze._est_lien(l) and l is not link
                    and l.LinkedObject is not None and replace._same_part(l, link, doc)]
    if dry_run:
        return {"replaced": [l.Name for l in targets], "refrozen": [],
                "object": object_name or old_name, "file": path, "dry_run": True}
    src_doc = docs.open_source(path, keep=doc)
    new_obj = src_doc.getObject(object_name or old_name)
    if new_obj is None:
        raise SourceNotFoundError(tr("Lightweight: object {obj} not found in {file}.").format(
            obj=object_name or old_name, file=path), file=path, object=object_name or old_name)
    to_freeze = []
    doc.openTransaction(tr("Replace component"))
    try:
        for l in targets:
            if replace.replace_link(doc, l, new_obj):
                to_freeze.append(l)
        freeze.marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()
    if to_freeze:
        freeze.figer(doc, to_freeze)
    return {"replaced": [l.Name for l in targets], "refrozen": [l.Name for l in to_freeze],
            "object": new_obj.Name, "file": path}


def duplicate_components(doc, names, with_joints=False):
    """Clone the components `names` in their assembly (same target, place and
    colours), with their joints when `with_joints`.
    -> {"clones": [{"source", "clone"}], "joints": [new joint names]}"""
    from . import duplicate
    doc = _doc(doc)
    comps = _objs(doc, names)
    before = set(o.Name for o in doc.Objects)
    clones = duplicate.duplicate(doc, comps, with_joints=with_joints)
    new_joints = [o.Name for o in doc.Objects if o.Name not in before and
                  ("JointType" in o.PropertiesList or "ObjectToGround" in o.PropertiesList)]
    return {"clones": [{"source": c.Name, "clone": n.Name} for c, n in zip(comps, clones)],
            "joints": new_joints}


def make_lightweight(doc, names=None, dry_run=False):
    """Replace the components `names` (None = every component of the
    assemblies) by lightweight ones: skeleton + mesh skins, joints kept.
    -> {"lightweight": [Link names], "containers": [names]}"""
    from . import freeze, lightweight
    doc = _doc(doc)
    if names is None:
        links = [l for l in doc.Objects if freeze._est_lien(l) and l.LinkedObject is not None
                 and not lightweight.is_lightweight(l.LinkedObject)
                 and any(a in l.InListRecursive for a in _assemblies(doc))]
    else:
        links = [l for l in _objs(doc, names) if freeze._est_lien(l)]
    if dry_run:
        return {"lightweight": [l.Name for l in links], "containers": [], "dry_run": True}
    doc.openTransaction(tr("Make lightweight"))
    try:
        made = lightweight.make(doc, links)
        freeze.marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()
    return {"lightweight": [l.Name for l in links if lightweight.is_lightweight(l.LinkedObject)],
            "containers": [c.Name for c in made]}


def restore_full(doc, names=None, dry_run=False):
    """Put lightweight components back to their source parts, joints included;
    frozen ones are frozen again. -> {"restored": [...], "refrozen": [...]}"""
    from . import freeze, lightweight
    doc = _doc(doc)
    links = [l for l in (doc.Objects if names is None else _objs(doc, names))
             if freeze._est_lien(l) and lightweight.is_lightweight(l.LinkedObject)]
    if dry_run:
        return {"restored": [l.Name for l in links], "refrozen": [], "dry_run": True}
    doc.openTransaction(tr("Restore full components"))
    try:
        done, to_freeze = lightweight.restore(doc, links)
        doc.recompute()
    finally:
        doc.commitTransaction()
    if to_freeze:
        freeze.figer(doc, to_freeze)
    return {"restored": [l.Name for l in done], "refrozen": [l.Name for l in to_freeze]}


def new_part_from_selection(doc, selection, path, label=None, linked=False, insert=True):
    """Create the part file `path` holding a Body with a SubShapeBinder of the
    `selection` = [[root object name, subname], ...] (e.g.
    [["Assembly", "Plate.Face6"]]). Default: independent copy (detached
    binder), inserted into the assembly at its place. `linked`: binder that
    follows the assembly (not inserted: the files would depend on each other).
    -> {"path", "document", "body", "binder", "inserted": Link name or None}"""
    from . import new_part
    doc = _doc(doc)
    if not doc.FileName:
        raise NoDocumentError(tr("Save the assembly first: the binder of the new part "
                                 "refers to it by its file."), document=doc.Name)
    keys = [(_obj(doc, r), s) for r, s in selection]
    if linked:
        new_doc, body, binder = new_part.create_part(
            path, supports=new_part.binder_supports(keys), label=label, source=doc.FileName)
        link = None
    else:
        shape, _failed = new_part.copy_shape(keys)
        if shape is None:
            raise UnsupportedObjectError(tr("The selected elements could not be read: "
                                            "nothing was created (see the report view)."))
        new_doc, body, binder = new_part.create_part(path, label=label, shape=shape,
                                                     source=doc.FileName)
        link = new_part.insert_into_assembly(doc, body)[0] if insert else None
    return {"path": path, "document": new_doc.Name, "body": body.Name, "binder": binder.Name,
            "inserted": link.Name if link is not None else None}


# ----------------------------------------------------------------------
#  Selection sets
# ----------------------------------------------------------------------
def selection_sets(doc):
    """Selection sets stored in `doc`. -> [{"name", "label", "members": [...]}]
    A member is "RootName|sub.path." (object) or "RootName|sub.path.Face6"."""
    from . import selection_sets as ss
    doc = _doc(doc)
    return [{"name": s.Name, "label": s.Label, "members": ss.get_members(s)}
            for s in ss.list_sets(doc)]


def create_selection_set(doc, label, members):
    """Store a new selection set. -> {"name", "label", "members"}"""
    from . import selection_sets as ss
    doc = _doc(doc)
    doc.openTransaction(tr("New selection set"))
    try:
        s = ss.create_set(doc, label, list(members))
    finally:
        doc.commitTransaction()
    return {"name": s.Name, "label": s.Label, "members": ss.get_members(s)}


def selection_set_members(doc, name, expand=False):
    """Members of the set `name`; `expand` lists individual parts (element
    members kept as they are). -> [member keys]"""
    from . import selection_sets as ss
    doc = _doc(doc)
    s = _obj(doc, name)
    members = ss.get_members(s)
    return ss.expand(doc, members) if expand else members


def combine_selection_sets(doc, a, b, op, label=None):
    """New set from the sets `a` and `b`: op = "union" | "intersection" |
    "difference" (on individual parts). -> {"name", "label", "members"}"""
    from . import selection_sets as ss
    doc = _doc(doc)
    ka = ss.expand(doc, ss.get_members(_obj(doc, a)))
    kb = ss.expand(doc, ss.get_members(_obj(doc, b)))
    sb = set(kb)
    if op == "union":
        res = ss.dedupe(ka + kb)
    elif op == "intersection":
        res = [k for k in ka if k in sb]
    elif op == "difference":
        res = [k for k in ka if k not in sb]
    else:
        raise UnsupportedObjectError("op must be union, intersection or difference", op=op)
    return create_selection_set(doc, label or "%s %s %s" % (a, op, b), res)


# ----------------------------------------------------------------------
#  Fasteners, GUI state
# ----------------------------------------------------------------------
def group_fasteners(doc, names=None):
    """Move fasteners of the Fasteners workbench into the Std_Part of their
    body (None = all). -> {"moved": [...], "parts_created": [...], "skipped": [...]}"""
    from . import fasteners
    doc = _doc(doc)
    moved, created, skipped = fasteners.organize(doc, _objs(doc, names))
    return {"moved": [o.Name for o in moved], "parts_created": [p.Name for p in created],
            "skipped": [o.Name for o in skipped]}


def reactivate_assembly(doc):
    """GUI only: clear a stuck task panel / edit / active object and activate
    the assembly again. -> {"active": bool}"""
    if not App.GuiUp:
        raise GuiRequiredError(tr("The operation needs the FreeCAD interface."))
    from . import reactivate
    return {"active": bool(reactivate.reactivate(_doc(doc)))}
