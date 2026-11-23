# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Panel models on real documents: OK is one undo step, Cancel (the model
never run) leaves the document unchanged."""

import os

import pytest

from conftest import open_doc, reopen

pytestmark = pytest.mark.freecad


def _outdated_doc(project):
    from freecad.assembly_companion import api
    folder = project("basic")
    doc = open_doc(os.path.join(folder, "assembly.FCStd"))
    api.freeze_parts(doc)
    doc = reopen(doc)
    future = os.path.getmtime(os.path.join(folder, "plate.FCStd")) + 3600
    os.utime(os.path.join(folder, "plate.FCStd"), (future, future))
    doc.UndoMode = 1
    return doc


def test_outdated_panel_accept_is_one_undo_step(project):
    from freecad.assembly_companion import outdated
    doc = _outdated_doc(project)
    undo = doc.UndoCount
    m = outdated.OutdatedPanel(doc)
    assert len(m.get("parts")) == 1
    assert m.run("refreeze") is True and len(m.result) == 1
    assert doc.UndoCount == undo + 1


def test_outdated_panel_cancel_changes_nothing(project):
    from freecad.assembly_companion import outdated
    doc = _outdated_doc(project)
    undo = doc.UndoCount
    before = {o.Name: o.FigeDate for o in doc.Objects if hasattr(o, "FigeDate")}
    m = outdated.OutdatedPanel(doc)
    m.set_row_checked("parts", m.get("parts")[0], False)
    assert doc.UndoCount == undo
    assert {o.Name: o.FigeDate for o in doc.Objects if hasattr(o, "FigeDate")} == before
