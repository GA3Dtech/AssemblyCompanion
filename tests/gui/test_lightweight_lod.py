# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Level of detail on native mesh skins: each display mode of the view
provider is wrapped in a SoLevelOfDetail (mesh / bounding box), once, and
updated when LodPixels changes."""

import time

import pytest

pytestmark = pytest.mark.gui


def process(n=10):
    from PySide import QtWidgets
    for _ in range(n):
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)


def lod_nodes(obj):
    from pivy import coin
    sw = obj.ViewObject.SwitchNode
    return [sw.getChild(i) for i in range(sw.getNumChildren())
            if sw.getChild(i).isOfType(coin.SoLevelOfDetail.getClassTypeId())]


@pytest.fixture
def skin():
    import FreeCAD as App
    import Mesh
    import Part
    doc = App.newDocument("ac_lod")
    sn = doc.addObject("Mesh::Feature", "Skin")
    sn.Mesh = Mesh.Mesh(Part.makeBox(10, 20, 30).tessellate(0.5))
    sn.addProperty("App::PropertyFloat", "LodPixels", "Lightweight", "")
    sn.LodPixels = 2000.0
    doc.recompute()
    yield sn
    App.closeDocument(doc.Name)


def test_attach_wraps_every_display_mode_once(skin):
    from freecad.assembly_companion import lightweight
    process()                                   # the creation observer may run first
    assert lightweight.attach_lod(skin)
    n = skin.ViewObject.SwitchNode.getNumChildren()
    lods = lod_nodes(skin)
    assert len(lods) == n and n > 0
    assert lightweight.attach_lod(skin)         # idempotent: no double wrapping
    assert len(lod_nodes(skin)) == n
    for lod in lod_nodes(skin):
        assert lod.getNumChildren() == 2
        assert not lod.getChild(0).isOfType(lod.getTypeId())
        assert lod.screenArea.getValues()[0] == 2000.0


def test_changed_threshold_updates_the_nodes(skin):
    from freecad.assembly_companion import lightweight
    lightweight.install()
    lightweight.attach_lod(skin)
    skin.LodPixels = 500.0
    process()
    assert all(lod.screenArea.getValues()[0] == 500.0 for lod in lod_nodes(skin))


def test_display_mode_still_switches(skin):
    from freecad.assembly_companion import lightweight
    lightweight.attach_lod(skin)
    for mode in skin.ViewObject.listDisplayModes():
        skin.ViewObject.DisplayMode = mode
        process(2)
    assert len(lod_nodes(skin)) == skin.ViewObject.SwitchNode.getNumChildren()


def test_skin_without_threshold_is_left_alone():
    import FreeCAD as App
    import Mesh
    import Part
    from freecad.assembly_companion import lightweight
    doc = App.newDocument("ac_lod_plain")
    try:
        sn = doc.addObject("Mesh::Feature", "Skin")
        sn.Mesh = Mesh.Mesh(Part.makeBox(1, 1, 1).tessellate(0.5))
        process()
        assert not lightweight.attach_lod(sn) and lod_nodes(sn) == []
    finally:
        App.closeDocument(doc.Name)
