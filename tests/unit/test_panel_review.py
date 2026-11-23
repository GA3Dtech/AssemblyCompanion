# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Review of the hand-built widget panels: a module that builds a dialog or a
form with widgets must be listed here with the reason, so that no panel is
written twice (once generated from a model, once by hand). Migrating a panel
to panel_model + bridge removes its entry."""

import os
import re

import pytest

pytestmark = pytest.mark.unit

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "freecad", "assembly_companion")

FORM = re.compile(r"QtWidgets\.(QDialog|QFormLayout|QGroupBox|QDockWidget)\(|"
                  r"class \w+\(QtWidgets\.(QDialog|QWidget)\)|self\.form = QtWidgets\.QWidget\(")

# module -> why its widgets are not (yet) generated from a model
ALLOWED = {
    "bridge.py": "the generic engine itself (WidgetForm, PanelDialog)",
    "prefs.py": "preference page: FreeCAD's own mechanism stays in widgets",
    "explorer.py": "thumbnail grid of thousands of files: custom QML candidate, postponed",
    "selection_sets.py": "dock with live tree, filters and 3D picking: not migrated yet",
    "align.py": "task panel driving 3D picking and a gizmo: not migrated yet",
}


def hand_built_modules():
    out = set()
    for name in sorted(os.listdir(PKG)):
        if name.endswith(".py"):
            with open(os.path.join(PKG, name), encoding="utf-8") as fh:
                if FORM.search(fh.read()):
                    out.add(name)
    return out


def test_every_hand_built_panel_is_listed_and_justified():
    found = hand_built_modules()
    assert found - set(ALLOWED) == set(), "new hand-built panel: use panel_model + bridge"
    assert set(ALLOWED) - found == set(), "stale entry: the panel was migrated, remove it"


def test_migrated_panels_have_no_widget_form():
    found = hand_built_modules()
    assert not {"outdated.py", "new_part.py", "collisions.py"} & found
