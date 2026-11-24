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
