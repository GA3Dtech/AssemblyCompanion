# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Generic panels (GUI): every QML component loads without error or warning
(a model using every parameter kind), the widgets fallback is used when Qt
Quick is unavailable, and both interfaces show the same parameters and
actions for every panel model."""

import os

import pytest

pytestmark = pytest.mark.gui

QML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "freecad", "assembly_companion", "resources", "qml")


def all_kinds_model():
    from freecad.assembly_companion import panel_model as pm

    class AllKinds(pm.PanelModel):
        title = "All kinds"
        hint = "Every parameter kind"

        def __init__(self):
            super().__init__()
            self.add(pm.Param("n", "Number", "number", 2.5, unit="mm"))
            self.add(pm.Param("i", "Integer", "int", 3))
            self.add(pm.Param("b", "Bool", "bool", True))
            self.add(pm.Param("c", "Choice", "choice", options=[("a", "A"), ("b", "B")]))
            self.add(pm.Param("col", "Color", "color", "#3366cc", section="More"))
            self.add(pm.Param("v", "Vector", "vector", [1, 2, 3], section="More"))
            self.add(pm.Param("p", "Path", "path", "/tmp", section="More"))
            self.add(pm.Param("t", "Text", "text", "abc", placeholder="…", section="More"))
            self.add(pm.Param("note", "A note", "note", section="More"))
            self.add(pm.Param("l", kind="list", columns=["A", "B"], section="List", rows=[
                {"id": "1", "cells": ["x", 1], "checked": True},
                {"id": "2", "cells": ["y", 2], "enabled": False}]))
            self.action(pm.Action("go", "Go", primary=True, accept=True))
            self.ran = []

        def trigger(self, name):
            self.ran.append(name)
    return AllKinds()


def panel_models():
    """Every panel model of the workbench, on a minimal document."""
    import FreeCAD as App
    from freecad.assembly_companion import (collisions, deps, extract, new_file, new_part,
                                            outdated, step_import, thumbs)
    doc = App.newDocument("ac_panels")
    box = doc.addObject("Part::Box", "Box")
    body = doc.addObject("PartDesign::Body", "Body")
    items = [("Box.", "Box"), ("Box001.", "Box001")]
    return doc, [all_kinds_model(), outdated.OutdatedPanel(doc),
                 new_part.NewPartPanel(doc, [(box, "Face6")]),
                 collisions.CollisionsPanel(doc, items, [(0, 1, 12.5, None)]),
                 step_import.ImportStepPanel(doc, "/tmp/kit.step"),
                 extract.ExtractPanel(doc, [body]),
                 new_file.NewFilePanel(doc),
                 deps.DependenciesPanel(doc),
                 thumbs.ThumbnailsPanel("/tmp")]


def item_names(item):
    """objectNames of the visual tree (Loader items have no QObject parent,
    findChild does not see them)."""
    names = {item.objectName()}
    for c in item.childItems():
        names |= item_names(c)
    return names


def process(n=10):
    from PySide import QtWidgets
    for _ in range(n):
        QtWidgets.QApplication.processEvents()


@pytest.fixture
def models():
    import FreeCAD as App
    doc, ms = panel_models()
    yield ms
    App.closeDocument(doc.Name)


def test_every_qml_file_is_used():
    names = set(os.listdir(QML_DIR))
    used = {"GenericPanel.qml"}
    for n in names:
        with open(os.path.join(QML_DIR, n), encoding="utf-8") as fh:
            text = fh.read()
        assert "import QtQuick 2.15" in text, n              # versioned: Qt 5 and Qt 6
        for other in names:
            if other != n and (other[:-4] + " {" in text or '"%s"' % other in text):
                used.add(other)
    assert used == names


def test_qml_loads_without_warning():
    from freecad.assembly_companion import bridge, qml_host
    if not qml_host.quick_usable():
        pytest.skip("Qt Quick unavailable")
    dlg = bridge.PanelDialog(all_kinds_model(), qml=True)
    try:
        assert dlg.is_qml
        dlg.show()
        process()
        assert dlg.form.qml_warnings == []
        names = item_names(dlg.form.rootObject())
        for name in ("input_n", "input_i", "toggle_b", "input_p", "input_t", "list_l",
                     "cancel"):
            assert name in names, name
    finally:
        dlg.close()
        dlg.deleteLater()


def test_qml_and_bridge_edit_the_model():
    from freecad.assembly_companion import bridge, qml_host
    if not qml_host.quick_usable():
        pytest.skip("Qt Quick unavailable")
    m = all_kinds_model()
    dlg = bridge.PanelDialog(m, qml=True)
    try:
        dlg.bridge.setValue("i", 5)
        dlg.bridge.setRowChecked("l", "1", False)
        process()
        assert m.get("i") == 5 and m.get("l") == []
        dlg.bridge.trigger("go")
        assert m.ran == ["go"] and dlg.result() == 1
    finally:
        dlg.deleteLater()


def test_fallback_without_qt_quick(monkeypatch):
    from freecad.assembly_companion import bridge, qml_host
    monkeypatch.setattr(qml_host, "forced_off", True)
    dlg = bridge.PanelDialog(all_kinds_model())
    try:
        assert not dlg.is_qml and isinstance(dlg.form, bridge.WidgetForm)
    finally:
        dlg.deleteLater()


def test_both_interfaces_show_the_same_parameters_and_actions(models, monkeypatch):
    from freecad.assembly_companion import bridge, qml_host
    for m in models:
        params = [p.name for p in m.params]
        actions = [a.name for a in m.actions]
        monkeypatch.setattr(qml_host, "forced_off", True)
        w = bridge.PanelDialog(m)
        assert list(w.form.editors) == params, type(m).__name__
        assert list(w.form.buttons) == actions, type(m).__name__
        w.deleteLater()
        monkeypatch.setattr(qml_host, "forced_off", False)
        if qml_host.quick_usable():
            q = bridge.PanelDialog(m, qml=True)
            assert q.is_qml, type(m).__name__
            assert [p["name"] for s in q.bridge.sections for p in s["params"]] == params
            assert [a["name"] for a in q.bridge.actions] == actions
            q.deleteLater()


def test_widget_form_edits_the_model(monkeypatch):
    from PySide import QtCore
    from freecad.assembly_companion import bridge, qml_host
    monkeypatch.setattr(qml_host, "forced_off", True)
    m = all_kinds_model()
    dlg = bridge.PanelDialog(m)
    try:
        f = dlg.form
        f.editors["i"][1].setValue(4)
        f.editors["t"][1].edit.textEdited.emit("new")
        f.editors["l"][1].row_items["1"].setCheckState(0, QtCore.Qt.Unchecked)
        assert m.get("i") == 4 and m.get("t") == "new" and m.get("l") == []
        f.buttons["go"].click()
        assert m.ran == ["go"]
    finally:
        dlg.deleteLater()


def test_row_click_list_in_both_interfaces(monkeypatch):
    from freecad.assembly_companion import bridge, panel_model as pm, qml_host

    class Clicks(pm.PanelModel):
        def __init__(self):
            super().__init__()
            self.clicked = []
            self.add(pm.Param("l", kind="list", checkable=False, columns=["A"],
                              rows=[{"id": "1", "cells": ["x"]}, {"id": "2", "cells": ["y"]}]))

        def row_clicked(self, name, row_id):
            self.clicked.append(row_id)

    monkeypatch.setattr(qml_host, "forced_off", True)
    m = Clicks()
    dlg = bridge.PanelDialog(m)
    tree = dlg.form.editors["l"][1]
    tree.itemClicked.emit(tree.row_items["2"], 0)
    assert m.clicked == ["2"] and m.get("l") == []
    dlg.deleteLater()
    monkeypatch.setattr(qml_host, "forced_off", False)
    if qml_host.quick_usable():
        q = bridge.PanelDialog(Clicks(), qml=True)
        assert q.is_qml and q.form.qml_warnings == []
        q.bridge.rowClicked("l", "1")
        assert q.model.clicked == ["1"]
        q.deleteLater()
