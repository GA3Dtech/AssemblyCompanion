# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Check dependencies (GUI): a hidden source document marked modified is
reported, and "ignore their changes" clears the flag FreeCAD checks before
asking to save the dependent files."""

import os
import sys

import pytest

pytestmark = pytest.mark.gui

HERE = os.path.dirname(os.path.abspath(__file__))


def test_modified_hidden_dependency_reported_then_ignored(tmp_path):
    import FreeCAD as App
    import FreeCADGui as Gui
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fixtures"))
    import build_fixtures
    from freecad.assembly_companion import api, deps
    before = set(App.listDocuments())
    try:
        folder = str(tmp_path / "basic")
        build_fixtures.build_basic(folder)
        for n in set(App.listDocuments()) - before:
            App.closeDocument(n)
        doc = App.openDocument(os.path.join(folder, "assembly.FCStd"))
        rows = api.analyze_dependencies(doc)
        plate = [r for r in rows if r["file"].endswith("plate.FCStd")][0]
        Gui.getDocument(plate["document"]).Modified = True
        rows = api.analyze_dependencies(doc)
        assert rows[0]["document"] == plate["document"] and rows[0]["modified"]
        model = deps.DependenciesPanel(doc)
        assert model.get("deps") == [plate["document"]]
        assert model.run("ignore") is True
        assert not Gui.getDocument(plate["document"]).Modified
    finally:
        for n in set(App.listDocuments()) - before:
            App.closeDocument(n)
