# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Freezing an imported STEP group keeps the colours: those of the solids
(ShapeAppearance) and the colour overrides of the Links (STEP importer of
the GUI). Built in a temporary folder, every document closed afterwards."""

import os
import sys

import pytest

pytestmark = pytest.mark.gui

HERE = os.path.dirname(os.path.abspath(__file__))


def _rgb(c):
    return tuple(round(x, 3) for x in tuple(c)[:3])


@pytest.fixture
def step_project(tmp_path):
    import FreeCAD as App
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fixtures"))
    import build_fixtures
    before = set(App.listDocuments())
    folder = str(tmp_path / "step_group")
    build_fixtures.build_step_group(folder)
    src = App.openDocument(os.path.join(folder, "pieces.FCStd"))
    mat = App.Material()
    mat.DiffuseColor = (0.8, 0.1, 0.1)
    src.getObject("Solid").ViewObject.ShapeAppearance = [mat]
    try:
        lk = src.getObject("AmeLink0").ViewObject
        lk.OverrideMaterial = True
        m2 = App.Material()
        m2.DiffuseColor = (0.1, 0.1, 0.9)
        lk.ShapeAppearance = [m2]
        src.save()
    except Exception:
        for n in set(App.listDocuments()) - before:
            App.closeDocument(n)
        raise
    yield folder
    for n in set(App.listDocuments()) - before:
        App.closeDocument(n)


def test_frozen_step_group_keeps_colours(step_project):
    import FreeCAD as App
    from freecad.assembly_companion import api
    doc = App.openDocument(os.path.join(step_project, "assembly.FCStd"))
    api.freeze_parts(doc, ["Group"])
    boitier = [o for o in doc.Objects if o.Label == "Boitier"][0]
    assert _rgb(boitier.ViewObject.ShapeAppearance[0].DiffuseColor) == (0.8, 0.1, 0.1)
    ame = [o for o in doc.Objects if o.isDerivedFrom("App::Link") and
           getattr(o, "FigeObjet", None) == "AmeLink0"][0]
    assert ame.ViewObject.OverrideMaterial
    assert _rgb(ame.ViewObject.ShapeAppearance[0].DiffuseColor) == (0.1, 0.1, 0.9)


def test_frozen_sub_assembly_joints_are_hidden(tmp_path):
    import FreeCAD as App
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fixtures"))
    import build_fixtures
    from freecad.assembly_companion import api
    before = set(App.listDocuments())
    try:
        folder = str(tmp_path / "subassembly")
        build_fixtures.build_subassembly(folder)
        for n in set(App.listDocuments()) - before:
            App.closeDocument(n)
        doc = App.openDocument(os.path.join(folder, "main.FCStd"))
        api.freeze_parts(doc, ["Sub"])
        fa = doc.getObject("Sub").LinkedObject
        joints = [j for g in fa.Group if g.TypeId == "Assembly::JointGroup" for j in g.Group]
        assert joints and not any(j.Visibility for j in joints)
    finally:
        for n in set(App.listDocuments()) - before:
            App.closeDocument(n)
