# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import STEP as part through the GUI importer (ImportGui: the user's import
settings, colours): no import group left, every solid shown by the
assembly, colours kept. Temporary files, documents closed afterwards."""

import pytest

pytestmark = pytest.mark.gui


def test_step_import_with_the_gui_importer(tmp_path):
    import FreeCAD as App
    import ImportGui
    import Part
    from freecad.assembly_companion import api
    before = set(App.listDocuments())
    try:
        d = App.newDocument("ac_step_src")
        top = d.addObject("App::Part", "Kit")
        a = d.addObject("Part::Feature", "Red")
        a.Shape = Part.makeBox(10, 10, 10)
        b = d.addObject("Part::Feature", "Blue")
        b.Shape = Part.makeBox(5, 5, 5, App.Vector(20, 0, 0))
        top.addObject(a)
        top.addObject(b)
        d.recompute()
        mat = App.Material()
        mat.DiffuseColor = (0.9, 0.1, 0.1)
        a.ViewObject.ShapeAppearance = [mat]
        step = str(tmp_path / "kit.step")
        ImportGui.export([top], step)
        App.closeDocument(d.Name)

        asm_doc = App.newDocument("ac_step_asm")
        asm_doc.saveAs(str(tmp_path / "asm.FCStd"))
        asm = asm_doc.addObject("Assembly::AssemblyObject", "Assembly")
        res = api.import_step(asm_doc, step)
        src = App.getDocument(res["document"])
        assert not [o for o in src.Objects if o.TypeId == "App::LinkGroup"]
        assert res["solids"] == 2
        assert len(Part.getShape(asm).Solids) == 2
        reds = [o for o in src.Objects if o.Label.startswith("Red")]
        colours = []
        for o in reds:
            vo = o.ViewObject
            if vo is not None and "ShapeAppearance" in vo.PropertiesList:
                colours.append(tuple(round(c, 1) for c in vo.ShapeAppearance[0].DiffuseColor[:3]))
        assert (0.9, 0.1, 0.1) in colours
    finally:
        for n in set(App.listDocuments()) - before:
            App.closeDocument(n)
