# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - frozen parts whose source file changed
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
outdated.py (Assembly Companion) - list the frozen parts whose source file
was modified after they were frozen, and refreeze the chosen ones.

Each frozen copy stores its source file and the date it was frozen
(properties FigeFichier / FigeFichierRelatif / FigeDate). A copy is out of
date when the source file is newer than that date. Refreezing updates the
copy (or the frozen Std_Part and its copies) in place from the SAVED source
file, then rewrites the joint references going through the Links that use
it (same names, hidden topological names flushed). If the source geometry
changed, some joint references may no longer match: run "Check frozen
assembly" afterwards.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import datetime

import FreeCAD as App

from . import freeze
from . import panel_model
from .i18n import tr

OUTDATED, UP_TO_DATE, MISSING = "outdated", "ok", "missing"


def _frozen_time(copy):
    try:
        return datetime.datetime.fromisoformat(copy.FigeDate).timestamp()
    except Exception:
        return None


def status(doc):
    """[(copy, source path or None, source mtime or None, state)] for every
    frozen copy / container of `doc` (not the copies inside a container)."""
    out = []
    for c in doc.Objects:
        if not freeze._est_fige(c) or c.getParentGeoFeatureGroup() is not None:
            continue
        path = freeze.chemin_source(c, doc)
        if path is None:
            out.append((c, None, None, MISSING))
            continue
        mtime = os.path.getmtime(path)
        frozen = _frozen_time(c)
        # 2 s of margin: file systems round modification times
        state = OUTDATED if frozen is None or mtime > frozen + 2 else UP_TO_DATE
        out.append((c, path, mtime, state))
    return out


def refreeze(doc, copies):
    """Update `copies` from their source file; returns the refreshed ones."""
    done = []
    doc.openTransaction(tr("Refreeze outdated parts"))
    try:
        for c in copies:
            doc_src, _opened = freeze._ouvrir_source(c, doc)
            src = freeze._objet_source(c, doc_src) if doc_src else None
            if src is None:
                App.Console.PrintWarning(tr("Refreeze: source of “{name}” not found ({file}).")
                                         .format(name=c.Label, file=c.FigeFichier) + "\n")
                continue
            links = [l for l in doc.Objects
                     if (freeze._est_lien(l) or freeze._est_assemblage_lien(l))
                     and l.LinkedObject is c]
            if "FigeBlocCarte" in c.PropertiesList:
                # Block: renumber the references from the old to the new block
                old = freeze.lire_carte(c)
                freeze._creer_ou_rafraichir_bloc(doc, src)
                new = freeze.lire_carte(c)
                for l in links:
                    freeze.appliquer_reecriture(l, fonction=lambda sub, k: (
                        freeze.renumeroter_vers_bloc(
                            freeze.renumeroter_depuis_bloc(sub, k, old), k, new)))
            elif freeze._est_conteneur_fige(c):
                freeze._creer_ou_rafraichir_conteneur(doc, src)
                for l in links:
                    if freeze._est_assemblage_lien(l):
                        continue        # its children keep their names
                    # Same object names in the refreshed container: keep the
                    # paths, flush the hidden names
                    freeze.appliquer_reecriture(l, chemins={})
            else:
                freeze._creer_ou_rafraichir_copie(doc, src)
                for l in links:
                    freeze.appliquer_reecriture(l)
            done.append(c)
            App.Console.PrintMessage(tr("Refreeze: “{name}” updated from {file}.").format(
                name=c.Label, file=os.path.basename(c.FigeFichier)) + "\n")
        freeze.marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()
    return done


# ----------------------------------------------------------------------
#  Panel (generic model: QML or widgets, see bridge.py)
# ----------------------------------------------------------------------
def _iso_date(text):
    try:
        return datetime.datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"


class OutdatedPanel(panel_model.PanelModel):
    """Frozen parts and their source file; refreezes the checked ones
    through api.refreeze_outdated (one undo step)."""

    width, height = 820, 440

    def __init__(self, doc):
        from . import api
        super().__init__()
        self.doc = doc
        self.title = tr("Frozen parts up to date?")
        self.cancel_label = tr("Close")
        rows = api.outdated_parts(doc)
        labels = {OUTDATED: tr("Out of date"), UP_TO_DATE: tr("Up to date"),
                  MISSING: tr("Source missing")}
        n_old = sum(1 for r in rows if r["state"] == OUTDATED)
        self.hint = tr("{old} frozen part(s) out of date: their source file was saved after "
                       "they were frozen. Checked parts are refrozen from the saved source "
                       "file.").format(old=n_old)
        self.add(panel_model.Param(
            "parts", kind="list",
            columns=[tr("Part"), tr("State"), tr("Frozen"), tr("Source saved"),
                     tr("Source file")],
            rows=[{"id": r["name"], "checked": r["state"] == OUTDATED,
                   "enabled": r["state"] != MISSING,
                   "cells": [r["label"], labels[r["state"]], _iso_date(r["frozen"]),
                             _iso_date(r["source_saved"]), r["source_file"]]}
                  for r in rows]))
        self.action(panel_model.Action("refreeze", tr("Refreeze checked parts"),
                                       primary=True, accept=True))

    def trigger(self, name):
        from . import api
        names = self.get("parts")
        self.result = api.refreeze_outdated(self.doc, names)["refrozen"] if names else []




def show(doc=None):
    """Report in a panel (QML or widgets), refreeze the checked parts."""
    from . import bridge, docs
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    rows = status(doc)
    if not rows:
        raise RuntimeError(tr("This document has no frozen parts."))
    n_old = sum(1 for r in rows if r[3] == OUTDATED)
    n_missing = sum(1 for r in rows if r[3] == MISSING)
    App.Console.PrintMessage(tr("Frozen parts: {total}, out of date: {old}, source "
                                "missing: {missing}.").format(
        total=len(rows), old=n_old, missing=n_missing) + "\n")
    model = OutdatedPanel(doc)
    if not bridge.show_panel(model) or not model.result:
        return []
    App.Console.PrintMessage(tr("Refreeze: {n} part(s) updated. Run “Check frozen "
                                "assembly” to verify the joints.").format(n=len(model.result))
                             + "\n")
    return [doc.getObject(n) for n in model.result]
