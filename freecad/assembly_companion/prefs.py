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
    "BomHierarchical": False,       # BOM with sub-assemblies as nodes (else flat)
    "FreezeMode": "structure",      # containers / sub-assemblies: "structure" or one "block"
    "ExplorerFullScan": "session",  # full library rescan when an explorer opens (always / session / manual)
    "ShowInAssemblyWorkbench": True,
    "UseQmlPanels": True,           # QML panels (widgets fallback without Qt Quick)
    "LeaveAssemblyForSelectionSets": True,
    "SelectionSetsElements": False,
    "LightweightLodPixels": 2000,   # LOD skins drawn as boxes below n pixels (0: plain mesh)  # selection sets store faces / edges / vertices
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


def _qtcore():
    try:
        from PySide import QtCore
    except ImportError:
        from PySide6 import QtCore
    return QtCore


def offer_clear_master_cache(old_master, parent=None):
    """The library folder changed: offer to delete the cache of the old one
    (scan and thumbnails), when there is one."""
    from . import library
    size = library.master_cache_bytes(old_master)
    if not size:
        return False
    QtWidgets = _qt()
    r = QtWidgets.QMessageBox.question(
        parent, tr("Parts library"),
        tr("The parts library folder changed. Delete the explorer cache of the previous "
           "folder ({size})?\n{path}").format(size=library.human_size(size), path=old_master),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
    if r != QtWidgets.QMessageBox.Yes:
        return False
    library.clear_cache(old_master)
    return True


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


class AssemblyCompanionPreferencePage(object):
    """FreeCAD Python preference page: `form` + loadSettings / saveSettings.
    Named apart from other addons' pages: FreeCAD keys Python pages by class
    name, and a page called "PreferencePage" (as in CroquisFreeCAD) showed
    the other addon's settings under both tabs."""

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
        self.use_qml = QtWidgets.QCheckBox(tr("Use the QML panels"))
        self.use_qml.setToolTip(
            tr("Panels drawn with Qt Quick. Unchecked, or when Qt Quick is not available, "
               "the same panels are shown with classic widgets."))
        f.addRow(self.use_qml)
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
        self.full_scan = QtWidgets.QComboBox()
        self.full_scan.addItem(tr("Every time an explorer opens"), "always")
        self.full_scan.addItem(tr("Once per FreeCAD session"), "session")
        self.full_scan.addItem(tr("Only with “Refresh all”"), "manual")
        self.full_scan.setToolTip(
            tr("The explorer shows the library from its cache at once. Files saved from "
               "FreeCAD refresh their own folder; a full rescan finds files added outside "
               "of FreeCAD."))
        f.addRow(tr("Full library scan:"), self.full_scan)
        row = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.cache_label = QtWidgets.QLabel()
        self.cache_label.setTextInteractionFlags(self.cache_label.textInteractionFlags()
                                                 | _qtcore().Qt.TextSelectableByMouse)
        h.addWidget(self.cache_label, 1)
        clear = QtWidgets.QPushButton(tr("Empty the cache"))
        clear.setToolTip(tr("Delete the saved folder scans and thumbnails of the explorer. "
                            "They are rebuilt at the next scan."))
        clear.clicked.connect(self._clear_cache)
        h.addWidget(clear)
        f.addRow(tr("Explorer cache:"), row)
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
        self.freeze_mode = QtWidgets.QComboBox()
        self.freeze_mode.addItem(tr("Keep their structure (parts, names, joints)"), "structure")
        self.freeze_mode.addItem(tr("One solid per component (lighter, rigid)"), "block")
        self.freeze_mode.setToolTip(
            tr("How Freeze copies a Std_Part, an imported STEP group or a sub-assembly. "
               "Sub-assemblies of the Assembly workbench always keep their structure."))
        f.addRow(tr("Freeze containers and sub-assemblies:"), self.freeze_mode)
        self.bom_tree = QtWidgets.QCheckBox(
            tr("Bill of materials by sub-assembly (hierarchical, else flat)"))
        f.addRow(self.bom_tree)
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
        self.lod.setRange(0, 1000000)
        self.lod.setSingleStep(500)
        self.lod.setToolTip(tr("Above 0, the skins of lightweight components are drawn as "
                               "boxes when they cover less than this screen area, in pixels "
                               "(2000: about 45 × 45). 0: plain mesh skins. Applies to "
                               "components made afterwards."))
        f.addRow(tr("Lightweight: box below (pixels):"), self.lod)
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

    def _show_cache(self):
        from . import library
        info = library.cache_info()
        self.cache_label.setText("%s  (%s)" % (library.human_size(info["bytes"]), info["path"]))

    def _clear_cache(self):
        from . import library
        QtWidgets = _qt()
        r = QtWidgets.QMessageBox.question(
            self.form, tr("Explorer cache"),
            tr("Delete the explorer cache? Folder scans and thumbnails are rebuilt at the "
               "next scan (slower once, on a network share)."),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if r == QtWidgets.QMessageBox.Yes:
            library.clear_cache()
            self._show_cache()

    def loadSettings(self):
        i = self.language.findData(get("Language"))
        self.language.setCurrentIndex(i if i >= 0 else 0)
        self.show_in_asm.setChecked(get("ShowInAssemblyWorkbench"))
        self.use_qml.setChecked(get("UseQmlPanels"))
        self.master_dir.edit.setText(get("LocalMasterDir"))
        self.new_dir.edit.setText(get("NewPartDir"))
        self._show_cache()
        i = self.full_scan.findData(get("ExplorerFullScan"))
        self.full_scan.setCurrentIndex(i if i >= 0 else 0)
        self.prefix.setText(get("NewPartPrefix"))
        self.digits.setValue(get("NewPartDigits"))
        self.revision.setText(get("NewPartRevision"))
        i = self.binder_mode.findData(get("NewPartBinderMode"))
        self.binder_mode.setCurrentIndex(i if i >= 0 else 0)
        self.insert_new.setChecked(get("NewPartInsert"))
        self.switch_wb.setChecked(get("NewPartSwitchWorkbench"))
        self.freeze_insert.setChecked(get("FreezeOnInsert"))
        self.bom_tree.setChecked(get("BomHierarchical"))
        i = self.freeze_mode.findData(get("FreezeMode"))
        self.freeze_mode.setCurrentIndex(i if i >= 0 else 0)
        self.leave_asm.setChecked(get("LeaveAssemblyForSelectionSets"))
        self.sets_elements.setChecked(get("SelectionSetsElements"))
        self.lod.setValue(get("LightweightLodPixels"))
        self.warn_close.setChecked(get("WarnOnSourceClose"))
        i = self.dup_joints.findData(get("DuplicateJoints"))
        self.dup_joints.setCurrentIndex(i if i >= 0 else 0)

    def saveSettings(self):
        put("Language", self.language.currentData())
        put("ShowInAssemblyWorkbench", self.show_in_asm.isChecked())
        put("UseQmlPanels", self.use_qml.isChecked())
        old, new = get("LocalMasterDir"), self.master_dir.edit.text().strip()
        if old and new and os.path.normcase(os.path.normpath(old)) != \
                os.path.normcase(os.path.normpath(new)):
            offer_clear_master_cache(old, self.form)
        put("LocalMasterDir", new)
        put("NewPartDir", self.new_dir.edit.text().strip())
        put("ExplorerFullScan", self.full_scan.currentData())
        put("NewPartPrefix", self.prefix.text().strip())
        put("NewPartDigits", self.digits.value())
        put("NewPartRevision", self.revision.text().strip())
        put("NewPartBinderMode", self.binder_mode.currentData())
        put("NewPartInsert", self.insert_new.isChecked())
        put("NewPartSwitchWorkbench", self.switch_wb.isChecked())
        put("FreezeOnInsert", self.freeze_insert.isChecked())
        put("FreezeMode", self.freeze_mode.currentData())
        put("BomHierarchical", self.bom_tree.isChecked())
        put("LeaveAssemblyForSelectionSets", self.leave_asm.isChecked())
        put("SelectionSetsElements", self.sets_elements.isChecked())
        put("LightweightLodPixels", self.lod.value())
        put("WarnOnSourceClose", self.warn_close.isChecked())
        put("DuplicateJoints", self.dup_joints.currentData())


def register():
    import FreeCADGui as Gui
    Gui.addPreferencePage(AssemblyCompanionPreferencePage, "Assembly Companion")
