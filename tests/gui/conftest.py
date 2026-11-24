# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI smoke tests: run inside the FreeCAD GUI (xvfb in CI, or the user's
FreeCAD of the developer). Skipped without the GUI."""

import pytest

try:
    import FreeCAD as App
except ImportError:
    App = None


def pytest_collection_modifyitems(config, items):
    if App is None or not App.GuiUp:
        skip = pytest.mark.skip(reason="needs the FreeCAD GUI")
        for it in items:
            if "tests/gui" in it.nodeid.replace("\\", "/"):
                it.add_marker(skip)


@pytest.fixture(autouse=True)
def no_modal_questions(monkeypatch):
    """A modal question left open would block the FreeCAD the tests run in
    (and the CI): during the GUI tests every Yes / No question answers No."""
    if App is None or not App.GuiUp:
        yield
        return
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    asked = []

    def question(*args, **kwargs):
        asked.append(args[2] if len(args) > 2 else "")
        return QtWidgets.QMessageBox.No
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", staticmethod(question))
    yield asked
