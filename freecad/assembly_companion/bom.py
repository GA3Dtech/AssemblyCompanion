# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - bill of materials including frozen parts
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
bom.py (Assembly Companion) - flat bill of materials of an assembly, frozen
parts included, exported as CSV.

A frozen part is a copy named "Fige_<label>" stored in the assembly: the
built-in BOM lists it under that name, or not at all inside a frozen Part.
Here every part is reported under its ORIGINAL name and source file (from
the FigeLabel / FigeFichier properties of the copy), whatever the way it is
used:
  * Link to a frozen copy or a frozen Std_Part (its copies are listed);
  * Link to a Body, a solid or a Std_Part of another file (still linked);
  * Body / solid stored in the assembly itself;
  * sub-assemblies, Std_Parts and groups, walked recursively;
  * Link arrays (ElementCount) multiply the quantities;
  * lightweight components count as the part they stand for.
Rows are grouped by (name, source file) and counted: clones, screws of the
Fasteners workbench (frozen or not) and repeated sub-assemblies add up.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import csv

import FreeCAD as App

from . import freeze
from .i18n import tr, language

FROZEN, LINKED, LOCAL, LIGHT = "frozen", "linked", "local", "lightweight"
_SKIP_TYPES = ("App::Origin", "App::OriginFeature", "App::Line", "App::Plane",
               "App::Point", "App::LocalCoordinateSystem", "Assembly::JointGroup",
               "Assembly::ViewGroup", "Assembly::BomGroup", "Assembly::SimulationGroup")


def _skip(o):
    if o.TypeId in _SKIP_TYPES:
        return True
    props = o.PropertiesList
    # joints, groundings, selection sets
    return "JointType" in props or "ObjectToGround" in props or \
        "SelectionSetMembers" in props


def _is_solid(o):
    try:
        return o.isDerivedFrom("Part::Feature") and not o.Shape.isNull() \
            and bool(o.Shape.Solids)
    except Exception:
        return False


def _children(o):
    """Children of a container that are not consumed by a sibling (tools of
    a boolean...). Joints are left out first: in an Assembly they sit next
    to the parts and reference all of them."""
    members = [c for c in (getattr(o, "Group", []) or []) if not _skip(c)]
    names = set(c.Name for c in members)
    return [c for c in members
            if not any(p.Name in names for p in c.InList if p is not o)]


def _file(doc):
    return os.path.basename(doc.FileName) if doc.FileName else doc.Label


def collect(roots, asm_doc):
    """{(name, source file, state): quantity} for the objects `roots`."""
    rows = {}

    def add(name, src, state, qty):
        key = (name, src, state)
        rows[key] = rows.get(key, 0) + qty

    def target(t, qty, state, depth):
        if depth > 50:
            return
        if "LWMap" in t.PropertiesList:         # lightweight component
            add(t.LWLabel or t.Label, os.path.basename(t.LWFile or ""), LIGHT, qty)
        elif freeze._est_conteneur_fige(t):
            for c in t.Group:
                if freeze._est_fige(c):
                    target(c, qty, FROZEN, depth + 1)
        elif freeze._est_copie_figee(t):
            add(t.FigeLabel or t.Label, os.path.basename(t.FigeFichier), FROZEN, qty)
        elif t.isDerivedFrom("PartDesign::Body") or (_is_solid(t) and
                                                     not t.isDerivedFrom("App::Part")):
            add(t.Label, _file(t.Document), state, qty)
        elif t.isDerivedFrom("App::Part") or t.hasExtension("App::GroupExtension"):
            for c in _children(t):
                walk(c, qty, state, depth + 1)

    def walk(o, qty, state, depth):
        if _skip(o) or o is None:
            return
        if o.isDerivedFrom("App::Link"):
            t = o.LinkedObject
            if t is None:
                return
            n = max(1, getattr(o, "ElementCount", 0) or 0)
            st = state if t.Document is asm_doc else LINKED
            target(t, qty * n, st, depth + 1)
        else:
            target(o, qty, state, depth)

    for r in roots:
        walk(r, 1, LOCAL, 0)
    return rows


def roots_of(doc):
    """Top-level assemblies of `doc`, else its root objects (Std_Part file)."""
    asms = [o for o in doc.Objects if o.isDerivedFrom("Assembly::AssemblyObject")
            and not any(p.isDerivedFrom("Assembly::AssemblyObject") for p in o.InList)]
    if asms:
        return asms
    return [o for o in doc.RootObjects if o.Name != freeze.GROUPE_COPIES]


def write_csv(path, rows):
    """Sorted rows; ';' separator for languages using a decimal comma (what
    their spreadsheets expect), ',' otherwise."""
    sep = ";" if language() in ("fr", "de", "it", "es") else ","
    state_txt = {FROZEN: tr("frozen"), LINKED: tr("linked"), LOCAL: tr("in the assembly"),
                 LIGHT: tr("lightweight")}
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=sep)
        w.writerow([tr("Quantity"), tr("Part"), tr("Source file"), tr("State")])
        for (name, src, state), qty in sorted(rows.items(),
                                              key=lambda kv: (kv[0][0].lower(), kv[0][1])):
            w.writerow([qty, name, src, state_txt[state]])


def export(doc=None):
    """Ask for the CSV file and write the BOM of the active document."""
    import FreeCADGui as Gui
    from . import docs
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    from . import api
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    rows = api.bom(doc)
    if not rows:
        raise RuntimeError(tr("No part found in this document."))
    base = os.path.splitext(doc.FileName)[0] if doc.FileName else \
        os.path.join(os.path.expanduser("~"), doc.Label)
    path, _f = QtWidgets.QFileDialog.getSaveFileName(
        Gui.getMainWindow(), tr("Export the bill of materials"),
        base + "_BOM.csv", tr("CSV files (*.csv)"))
    if not path:
        return None
    if not path.lower().endswith(".csv"):
        path += ".csv"
    api.export_bom_csv(doc, path)
    total = sum(r["quantity"] for r in rows)
    App.Console.PrintMessage(tr("BOM: {n} different part(s), {total} in all, written to "
                                "{file}").format(n=len(rows), total=total, file=path) + "\n")
    return path
