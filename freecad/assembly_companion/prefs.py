# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - preferences
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
prefs.py (Assembly Companion) - every setting of the workbench in one place
(parameter group Mod/AssemblyCompanion), plus the "Assembly Companion" page
of Edit > Preferences.

Modules read settings through get() / put() with the keys defined in
DEFAULTS, never with their own ParamGet calls, so the preference page always
shows every setting. Existing keys (LocalMasterDir, FreezeOnInsert,
ShowInAssemblyWorkbench) keep their names: they are already in users'
user.cfg.
"""

import os

import FreeCAD as App

from .i18n import tr, LANGUAGES

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/AssemblyCompanion"

# key -> default value (its type selects the parameter accessor)
DEFAULTS = {
    "Language": "auto",
    "LocalMasterDir": "",           # parts library root (explorer, insert)
    "FreezeOnInsert": False,
    "ShowInAssemblyWorkbench": True,
    "LeaveAssemblyForSelectionSets": True,
    "SelectionSetsElements": False,
    "LightweightLodFactor": 0,      # >0: LOD skins drawn as boxes beyond n x their size  # selection sets store faces / edges / vertices
    "WarnOnSourceClose": True,
    "DuplicateJoints": "ask",       # duplicate: also copy joints (ask / always / never)      # close_guard: warn when a linked source is closed
    "NewPartDir": "",               # working folder ("" = folder of the assembly)
    "NewPartPrefix": "",
    "NewPartDigits": 3,
    "NewPartRevision": "a",
    "NewPartInsert": True,          # insert the new part into the assembly
    "NewPartSwitchWorkbench": True,  # switch to PartDesign after creation
    "NewPartBinderMode": "copy",    # "copy" (detached binder) or "linked"
    "NewPartLastDir": "",           # last folder / prefix used (not on the page)
    "NewPartLastPrefix": "",
}


def _grp():
    return App.ParamGet(PARAM_PATH)


def get(key):
    default = DEFAULTS[key]
    g = _grp()
    try:
        if isinstance(default, bool):
            return g.GetBool(key, default)
        if isinstance(default, int):
            return g.GetInt(key, default)
        return g.GetString(key, default)
    except Exception:
        return default


def put(key, value):
    default = DEFAULTS[key]
    g = _grp()
    if isinstance(default, bool):
        g.SetBool(key, bool(value))
    elif isinstance(default, int):
        g.SetInt(key, int(value))
    else:
        g.SetString(key, value or "")


# ----------------------------------------------------------------------
#  Preference page (Edit > Preferences > Assembly Companion)
# ----------------------------------------------------------------------
def _qt():
    try:
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets
    return QtWidgets


class _FolderField(object):
    """Line edit + browse button for a folder."""

    def __init__(self, parent, title):
        QtWidgets = _qt()
        self.widget = QtWidgets.QWidget(parent)
        lay = QtWidgets.QHBoxLayout(self.widget)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QtWidgets.QLineEdit()
        btn = QtWidgets.QPushButton(tr("Browse…"))
        lay.addWidget(self.edit, 1)
        lay.addWidget(btn)
        self._title = title
        btn.clicked.connect(self._browse)

    def _browse(self):
        QtWidgets = _qt()
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self.widget, self._title, self.edit.text() or os.path.expanduser("~"))
        if d:
            self.edit.setText(d)


class PreferencePage(object):
    """FreeCAD Python preference page: `form` + loadSettings / saveSettings."""

    def __init__(self, parent=None):
        QtWidgets = _qt()
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(tr("General"))
        lay = QtWidgets.QVBoxLayout(self.form)

        # --- interface
        g = QtWidgets.QGroupBox(tr("Interface"))
        f = QtWidgets.QFormLayout(g)
        self.language = QtWidgets.QComboBox()
        self.language.addItem(tr("Same as FreeCAD"), "auto")
        for code, name in LANGUAGES:
            self.language.addItem(name, code)
        f.addRow(tr("Language:"), self.language)
        self.show_in_asm = QtWidgets.QCheckBox(
            tr("Show the Assembly Companion toolbar in the Assembly workbench"))
        f.addRow(self.show_in_asm)
        note = QtWidgets.QLabel(tr("Language and toolbar changes apply after restarting FreeCAD."))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        f.addRow(note)
        lay.addWidget(g)

        # --- folders
        g = QtWidgets.QGroupBox(tr("Folders"))
        f = QtWidgets.QFormLayout(g)
        self.master_dir = _FolderField(self.form, tr("Parts library folder"))
        self.master_dir.edit.setToolTip(
            tr("Root folder holding all your part folders (visual insertion, local explorer)."))
        f.addRow(tr("Parts library:"), self.master_dir.widget)
        self.new_dir = _FolderField(self.form, tr("Working folder for new parts"))
        self.new_dir.edit.setPlaceholderText(tr("Empty: folder of the assembly"))
        f.addRow(tr("Working folder:"), self.new_dir.widget)
        lay.addWidget(g)

        # --- new part from selection
        g = QtWidgets.QGroupBox(tr("New part from selection"))
        f = QtWidgets.QFormLayout(g)
        self.prefix = QtWidgets.QLineEdit()
        self.prefix.setPlaceholderText(tr("e.g. AB"))
        f.addRow(tr("Default prefix:"), self.prefix)
        self.digits = QtWidgets.QSpinBox()
        self.digits.setRange(1, 6)
        f.addRow(tr("Digits of the number:"), self.digits)
        self.revision = QtWidgets.QLineEdit()
        f.addRow(tr("First revision:"), self.revision)
        self.binder_mode = QtWidgets.QComboBox()
        self.binder_mode.addItem(tr("Independent copy (recommended)"), "copy")
        self.binder_mode.addItem(tr("Linked to the assembly (follows its changes)"), "linked")
        f.addRow(tr("Binder:"), self.binder_mode)
        self.insert_new = QtWidgets.QCheckBox(tr("Insert the new part into the active assembly"))
        f.addRow(self.insert_new)
        self.switch_wb = QtWidgets.QCheckBox(tr("Switch to the Part Design workbench"))
        f.addRow(self.switch_wb)
        lay.addWidget(g)

        # --- behaviour
        g = QtWidgets.QGroupBox(tr("Behaviour"))
        f = QtWidgets.QFormLayout(g)
        self.freeze_insert = QtWidgets.QCheckBox(tr("Freeze parts on visual insertion"))
        f.addRow(self.freeze_insert)
        self.leave_asm = QtWidgets.QCheckBox(
            tr("Leave the assembly edit mode when opening selection sets"))
        self.leave_asm.setToolTip(
            tr("In assembly edit mode a click selects whole parts and drags them; "
               "outside of it faces, edges and vertices can be selected."))
        f.addRow(self.leave_asm)
        self.sets_elements = QtWidgets.QCheckBox(
            tr("Selection sets keep faces, edges and vertices"))
        f.addRow(self.sets_elements)
        self.lod = QtWidgets.QSpinBox()
        self.lod.setRange(0, 1000)
        self.lod.setToolTip(tr("Above 0, the skins of lightweight components are drawn as "
                               "boxes when the camera is farther than this many times their "
                               "size (experimental, e.g. 40). 0: plain mesh skins. Applies to "
                               "components made afterwards."))
        f.addRow(tr("Lightweight: box beyond (× size):"), self.lod)
        self.warn_close = QtWidgets.QCheckBox(
            tr("Warn when a file used by linked parts of an open assembly is closed"))
        self.warn_close.setToolTip(
            tr("Closing such a file makes its parts vanish from the assembly; "
               "the warning offers to freeze them."))
        f.addRow(self.warn_close)
        self.dup_joints = QtWidgets.QComboBox()
        self.dup_joints.addItem(tr("Ask"), "ask")
        self.dup_joints.addItem(tr("Always"), "always")
        self.dup_joints.addItem(tr("Never"), "never")
        f.addRow(tr("Duplicate the joints with the components:"), self.dup_joints)
        lay.addWidget(g)
        lay.addStretch(1)

    def loadSettings(self):
        i = self.language.findData(get("Language"))
        self.language.setCurrentIndex(i if i >= 0 else 0)
        self.show_in_asm.setChecked(get("ShowInAssemblyWorkbench"))
        self.master_dir.edit.setText(get("LocalMasterDir"))
        self.new_dir.edit.setText(get("NewPartDir"))
        self.prefix.setText(get("NewPartPrefix"))
        self.digits.setValue(get("NewPartDigits"))
        self.revision.setText(get("NewPartRevision"))
        i = self.binder_mode.findData(get("NewPartBinderMode"))
        self.binder_mode.setCurrentIndex(i if i >= 0 else 0)
        self.insert_new.setChecked(get("NewPartInsert"))
        self.switch_wb.setChecked(get("NewPartSwitchWorkbench"))
        self.freeze_insert.setChecked(get("FreezeOnInsert"))
        self.leave_asm.setChecked(get("LeaveAssemblyForSelectionSets"))
        self.sets_elements.setChecked(get("SelectionSetsElements"))
        self.lod.setValue(get("LightweightLodFactor"))
        self.warn_close.setChecked(get("WarnOnSourceClose"))
        i = self.dup_joints.findData(get("DuplicateJoints"))
        self.dup_joints.setCurrentIndex(i if i >= 0 else 0)

    def saveSettings(self):
        put("Language", self.language.currentData())
        put("ShowInAssemblyWorkbench", self.show_in_asm.isChecked())
        put("LocalMasterDir", self.master_dir.edit.text().strip())
        put("NewPartDir", self.new_dir.edit.text().strip())
        put("NewPartPrefix", self.prefix.text().strip())
        put("NewPartDigits", self.digits.value())
        put("NewPartRevision", self.revision.text().strip())
        put("NewPartBinderMode", self.binder_mode.currentData())
        put("NewPartInsert", self.insert_new.isChecked())
        put("NewPartSwitchWorkbench", self.switch_wb.isChecked())
        put("FreezeOnInsert", self.freeze_insert.isChecked())
        put("LeaveAssemblyForSelectionSets", self.leave_asm.isChecked())
        put("SelectionSetsElements", self.sets_elements.isChecked())
        put("LightweightLodFactor", self.lod.value())
        put("WarnOnSourceClose", self.warn_close.isChecked())
        put("DuplicateJoints", self.dup_joints.currentData())


def register():
    import FreeCADGui as Gui
    Gui.addPreferencePage(PreferencePage, "Assembly Companion")
