# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Smoke tests of the workbench in the FreeCAD GUI. They create their own
temporary documents and close them; the user's documents are not touched."""

import os

import pytest

pytestmark = pytest.mark.gui

try:
    import FreeCAD as App
    import FreeCADGui as Gui
except ImportError:
    App = Gui = None


@pytest.fixture
def temp_doc():
    docs = []

    def _new(name="AC_GUI_TEST"):
        d = App.newDocument(name)
        docs.append(d)
        return d
    yield _new
    for d in docs:
        try:
            App.closeDocument(d.Name)
        except Exception:
            pass


def test_workbench_activates():
    before = Gui.activeWorkbench().name()
    try:
        Gui.activateWorkbench("AssemblyCompanionWorkbench")
        assert Gui.activeWorkbench().name() == "AssemblyCompanionWorkbench"
    finally:
        Gui.activateWorkbench(before)


def test_every_command_registered_with_its_icon():
    from freecad.assembly_companion import commands, icon
    registered = set(Gui.listCommands())
    for name, cmd in commands.COMMANDS.items():
        assert name in registered, name
        assert os.path.isfile(icon(cmd._icon)), cmd._icon


def test_toolbar_declared_in_assembly_workbench():
    from freecad.assembly_companion import commands, init_gui, prefs
    if not prefs.get("ShowInAssemblyWorkbench"):
        pytest.skip("toolbar disabled in the preferences")
    grp = App.ParamGet(init_gui.ASM_TOOLBARS)
    assert grp.HasGroup(init_gui.ASM_TOOLBAR_GROUP)
    bar = grp.GetGroup(init_gui.ASM_TOOLBAR_GROUP)
    assert bar.GetString("Name") == init_gui.ASM_TOOLBAR_NAME
    keys = [k for t, k, *_ in bar.GetContents() if t == "String"]
    for cmd in [c for c in commands.TOOLBAR if c != "Separator"]:
        assert cmd in keys, cmd


def test_preference_page_builds_and_loads():
    from freecad.assembly_companion import prefs
    page = prefs.AssemblyCompanionPreferencePage()
    page.loadSettings()
    assert page.form.windowTitle()
    page.form.deleteLater()


@pytest.mark.parametrize("key", ["assembly", "part"])
def test_active_assembly_found_with_both_keys(temp_doc, key):
    """26.x stores the active assembly under "assembly", 1.0 under "part"."""
    import AssemblyApp  # noqa: F401
    from freecad.assembly_companion import explorer
    d = temp_doc()
    a1 = d.addObject("Assembly::AssemblyObject", "Assembly")
    d.addObject("Assembly::AssemblyObject", "Assembly001")    # two: no fallback
    d.recompute()
    view = Gui.getDocument(d.Name).ActiveView
    for k in ("assembly", "part"):
        view.setActiveObject(k, None)
    view.setActiveObject(key, a1)
    assert explorer._target_container(d) is a1


def test_close_guard_detects_linked_source(temp_doc, tmp_path, monkeypatch):
    from freecad.assembly_companion import close_guard
    from PySide import QtWidgets
    for _ in range(5):              # closings of earlier tests, deferred by the guard
        QtWidgets.QApplication.processEvents()
    calls = []
    monkeypatch.setattr(close_guard, "_guarded", lambda path, label, deps: calls.append(deps))
    guard = close_guard._CloseGuard()
    App.addDocumentObserver(guard)
    try:
        src = temp_doc("AC_GUI_SRC")
        box = src.addObject("Part::Box", "Box")
        src.recompute()
        src.saveAs(str(tmp_path / "src.FCStd"))
        asm = temp_doc("AC_GUI_ASM")
        asm.saveAs(str(tmp_path / "asm.FCStd"))
        lk = asm.addObject("App::Link", "L")
        lk.setLink(box)
        asm.recompute()
        App.closeDocument(src.Name)
        from PySide import QtWidgets
        QtWidgets.QApplication.processEvents()      # the guard defers with a timer
        assert {asm.Name: ["L"]} in calls       # other closings may be reported too
    finally:
        App.removeDocumentObserver(guard)
