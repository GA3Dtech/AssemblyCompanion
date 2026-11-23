# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Freeze / relink / diagnostic / unused copies, through the API."""

import os
import shutil

import pytest

from conftest import close_all, open_doc, placements, reopen, same_placements

pytestmark = pytest.mark.freecad


def _api():
    from freecad.assembly_companion import api
    return api


def test_freeze_survives_missing_sources_then_relink(project):
    api = _api()
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    before = placements(doc)
    res = api.freeze_parts(doc)
    assert sorted(res["frozen"]) == ["Block", "Pin", "Plate"]
    assert res["refs_updated"] > 0
    from freecad.assembly_companion import freeze
    assert freeze.liens_externes(doc) == []
    doc.save()
    close_all()
    # sources gone: the assembly must reopen and resolve on its own
    hidden = os.path.join(folder, "hidden")
    os.makedirs(hidden)
    for f in ("plate.FCStd", "pin.FCStd", "block.FCStd"):
        shutil.move(os.path.join(folder, f), hidden)
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    d = api.diagnose(doc)
    assert d["broken"] == 0 and d["ok"] > 0
    assert all(c["topo_history"] == 0 for c in d["copies"])
    assert doc.getObject("Assembly").solve() == 0
    assert same_placements(before, placements(doc))
    copies_before = sorted(o.Name for o in doc.Objects if freeze._est_fige(o))
    # sources back: relink, then freeze again reuses the same copies
    for f in os.listdir(hidden):
        shutil.move(os.path.join(hidden, f), folder)
    r = api.relink_parts(doc)
    assert sorted(r["relinked"]) == ["Block", "Pin", "Plate"]
    assert all(doc.getObject(n).LinkedObject.Document is not doc for n in r["relinked"])
    api.freeze_parts(doc)
    assert sorted(o.Name for o in doc.Objects if freeze._est_fige(o)) == copies_before
    assert api.diagnose(doc)["broken"] == 0


def test_dry_run_changes_nothing(project):
    api = _api()
    doc = open_doc(os.path.join(project("basic"), "assembly.FCStd"))
    res = api.freeze_parts(doc, dry_run=True)
    assert res["dry_run"] and sorted(res["frozen"]) == ["Block", "Pin", "Plate"]
    from freecad.assembly_companion import freeze
    assert len(freeze.liens_externes(doc)) == 3


def test_frozen_std_part_keeps_joints(project):
    api = _api()
    from freecad.assembly_companion import freeze
    doc = open_doc(os.path.join(project("std_part"), "assembly.FCStd"))
    api.freeze_parts(doc)
    doc = reopen(doc)
    cont = [o for o in doc.Objects if freeze._est_conteneur_fige(o)]
    assert len(cont) == 1
    assert sorted(c.FigeObjet for c in cont[0].Group if freeze._est_copie_figee(c)) == \
        ["Left", "Right"]
    assert api.diagnose(doc)["broken"] == 0
    assert doc.getObject("Assembly").solve() == 0


def test_unused_copy_goes_to_unused_and_back(project):
    api = _api()
    from freecad.assembly_companion import freeze
    doc = open_doc(os.path.join(project("basic"), "assembly.FCStd"))
    api.freeze_parts(doc)
    block = doc.getObject("Block")
    copy = block.LinkedObject
    api.delete_part_joints(doc, ["Block"])
    doc.removeObject("Block")
    freeze.marquer_inutilisees(doc)
    unused = doc.getObject(freeze.GROUPE_INUTILES)
    assert unused is not None and copy in unused.Group
    assert api.diagnose(doc)["unused_copies"] == [copy.Name]
    lk = doc.addObject("App::Link", "Again")
    lk.setLink(copy)
    doc.getObject("Assembly").addObject(lk)
    freeze.marquer_inutilisees(doc)
    assert copy in doc.getObject(freeze.GROUPE_COPIES).Group
    assert doc.getObject(freeze.GROUPE_INUTILES) is None


def test_diagnose_reports_a_broken_reference(project):
    api = _api()
    doc = open_doc(os.path.join(project("basic"), "assembly.FCStd"))
    assert api.diagnose(doc)["broken"] == 0
    j = [o for o in doc.Objects if getattr(o, "JointType", "") == "Fixed"][0]
    base, subs = j.Reference1
    j.Reference1 = (base, ["Face999", "Face999"])
    d = api.diagnose(doc)
    assert d["broken"] == 2
    assert {r["sub"] for r in d["references"] if not r["ok"]} == {"Face999"}


def test_outdated_detected_then_refrozen(project):
    api = _api()
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    api.freeze_parts(doc)
    doc = reopen(doc)
    assert {r["state"] for r in api.outdated_parts(doc)} == {"ok"}
    future = os.path.getmtime(os.path.join(folder, "plate.FCStd")) + 3600
    os.utime(os.path.join(folder, "plate.FCStd"), (future, future))
    states = {r["label"]: r["state"] for r in api.outdated_parts(doc)}
    assert states["Plate"] == "outdated" and states["Pin"] == "ok"
    res = api.refreeze_outdated(doc)
    assert len(res["refrozen"]) == 1
    assert api.diagnose(doc)["broken"] == 0
