# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - generic panels: model <-> QML / widgets
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
bridge.py (Assembly Companion) - generic panels built from a panel model
(panel_model.py): the Bridge object between the model and its QML
(resources/qml/GenericPanel.qml), the WidgetForm fallback built from the
same model, and PanelDialog, which shows either in a dialog.

Adapted from dtpanels/bridge.py of ShowRoom
(https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later): Bridge,
_WidgetForm and make_theme, reduced to dialogs whose model calls api.py.
No business logic here: values go to the model, actions to model.run().
"""

import FreeCAD as App

try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

from . import qml_host
from .i18n import tr
from .i18n import tr as _translate      # dynamic texts from the QML


# ----------------------------------------------------------------------
#  Theme (colours and font of the running FreeCAD, light or dark)
# ----------------------------------------------------------------------
def make_theme():
    """Colours and font matching the running FreeCAD theme (from ShowRoom's
    make_theme, without the widget probing)."""
    app = QtWidgets.QApplication.instance()
    pal = app.palette() if app else QtGui.QPalette()
    try:
        import FreeCADGui as Gui
        pal = Gui.getMainWindow().palette()
    except Exception:
        pass
    win = QtGui.QColor(pal.color(QtGui.QPalette.Window))
    txt = QtGui.QColor(pal.color(QtGui.QPalette.WindowText))
    base = QtGui.QColor(pal.color(QtGui.QPalette.Base))
    accent = QtGui.QColor(pal.color(QtGui.QPalette.Highlight))
    if abs(txt.lightness() - win.lightness()) < 80:      # unreadable pair: plain contrast
        txt = QtGui.QColor("#f2f2f2" if win.lightness() < 128 else "#1a1a1a")
    font = QtGui.QFontInfo(QtWidgets.QApplication.font())
    px = font.pixelSize() if font.pixelSize() > 0 else 13

    def mix(a, b, k):
        return QtGui.QColor(int(a.red() + (b.red() - a.red()) * k),
                            int(a.green() + (b.green() - a.green()) * k),
                            int(a.blue() + (b.blue() - a.blue()) * k)).name()
    dark = win.lightness() < 128
    field = base.name() if abs(base.lightness() - win.lightness()) > 6 else mix(win, txt, 0.11)
    return {"dark": dark, "window": win.name(), "text": txt.name(), "family": font.family(),
            "s": max(0.9, px / 12.0), "card": mix(win, txt, 0.05), "field": field,
            "line": mix(win, txt, 0.22), "muted": mix(win, txt, 0.6),
            "accent": accent.name(),
            "accentText": "#ffffff" if accent.lightness() < 150 else "#101010",
            "bad": "#d6453d" if not dark else "#f0736b"}


# ----------------------------------------------------------------------
#  Bridge
# ----------------------------------------------------------------------
class I18n(QtCore.QObject):
    """`i18n` context object: the QML calls i18n.tr("...") (no qsTr), and
    tools/i18n.py scans the .qml files for these texts."""

    @QtCore.Slot(str, result=str)
    def tr(self, text):
        return _translate(text)


class Bridge(QtCore.QObject):
    """What the QML (and the WidgetForm) see of a panel model."""

    valuesChanged = QtCore.Signal()
    stateChanged = QtCore.Signal()
    heightChanged = QtCore.Signal(float)
    closeRequested = QtCore.Signal(bool)       # True = accepted

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self._theme = make_theme()
        self._sections = model.sections()
        self._actions = [a.public() for a in model.actions]

    def _values(self):
        return dict(self.model.values)

    sections = QtCore.Property("QVariant", lambda self: self._sections, constant=True)
    actions = QtCore.Property("QVariant", lambda self: self._actions, constant=True)
    theme = QtCore.Property("QVariant", lambda self: self._theme, constant=True)
    title = QtCore.Property(str, lambda self: self.model.title, constant=True)
    cancelLabel = QtCore.Property(str, lambda self: self.model.cancel_label or tr("Cancel"),
                                  constant=True)
    hint = QtCore.Property(str, lambda self: self.model.hint, notify=stateChanged)
    values = QtCore.Property("QVariant", _values, notify=valuesChanged)
    hidden = QtCore.Property("QVariant", lambda self: sorted(self.model.hidden),
                             notify=valuesChanged)
    error = QtCore.Property(str, lambda self: self.model.error, notify=stateChanged)

    def refresh(self):
        self.valuesChanged.emit()
        self.stateChanged.emit()

    @QtCore.Slot(float)
    def setContentHeight(self, h):
        self.heightChanged.emit(h)

    @QtCore.Slot(str, "QVariant")
    def setValue(self, name, value):
        self.model.set(name, value)
        self.refresh()

    @QtCore.Slot(str, str, bool)
    def setRowChecked(self, name, row_id, checked):
        self.model.set_row_checked(name, row_id, checked)
        self.refresh()

    @QtCore.Slot(str)
    def trigger(self, name):
        if name == "__cancel__":
            self.closeRequested.emit(False)
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            close = self.model.run(name)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.refresh()
        if close:
            self.closeRequested.emit(True)

    @QtCore.Slot(str)
    def browse(self, name):
        """Native file dialog of a path parameter."""
        p = self.model.param(name)
        start = self.model.browse_start(name)
        parent = QtWidgets.QApplication.activeWindow()
        if p.mode == "dir":
            path = QtWidgets.QFileDialog.getExistingDirectory(parent, p.label, start)
        elif p.mode == "save":
            path = QtWidgets.QFileDialog.getSaveFileName(parent, p.label, start, p.filter)[0]
        else:
            path = QtWidgets.QFileDialog.getOpenFileName(parent, p.label, start, p.filter)[0]
        if path:
            self.setValue(name, path)

    @QtCore.Slot(str)
    def pickColor(self, name):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.model.get(name)),
                                            QtWidgets.QApplication.activeWindow(),
                                            self.model.param(name).label)
        if c.isValid():
            self.setValue(name, c.name())


# ----------------------------------------------------------------------
#  Widgets fallback (same model, same parameters and actions)
# ----------------------------------------------------------------------
class WidgetForm(QtWidgets.QWidget):
    """Classic widgets built from the model, used without Qt Quick."""

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.editors = {}           # name -> (public param, widget)
        self.buttons = {}           # action name -> QPushButton
        lay = QtWidgets.QVBoxLayout(self)
        self.hint = QtWidgets.QLabel()
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        for sec in bridge.sections:
            box = QtWidgets.QGroupBox(sec["title"]) if sec["title"] else QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(box)
            if not sec["title"]:
                form.setContentsMargins(0, 0, 0, 0)
            for p in sec["params"]:
                w = self._editor(p)
                w.setToolTip(p["tip"])
                self.editors[p["name"]] = (p, w)
                if p["kind"] in ("note", "list", "bool"):
                    form.addRow(w)
                else:
                    form.addRow(p["label"], w)
            lay.addWidget(box, 1 if any(p["kind"] == "list" for p in sec["params"]) else 0)
        self.err = QtWidgets.QLabel()
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: %s;" % bridge.theme["bad"])
        lay.addWidget(self.err)
        bb = QtWidgets.QDialogButtonBox()
        for a in bridge.actions:
            b = bb.addButton(a["label"], QtWidgets.QDialogButtonBox.AcceptRole if a["accept"]
                             else QtWidgets.QDialogButtonBox.ActionRole)
            b.setToolTip(a["tip"])
            b.setDefault(a["primary"])
            b.clicked.connect(lambda _=False, n=a["name"]: bridge.trigger(n))
            self.buttons[a["name"]] = b
        cancel = bb.addButton(bridge.cancelLabel, QtWidgets.QDialogButtonBox.RejectRole)
        cancel.clicked.connect(lambda: bridge.trigger("__cancel__"))
        lay.addWidget(bb)
        bridge.valuesChanged.connect(self.sync)
        bridge.stateChanged.connect(self.sync_state)
        self.sync()
        self.sync_state()

    def _editor(self, p):
        name, kind, b = p["name"], p["kind"], self.bridge
        if kind == "bool":
            w = QtWidgets.QCheckBox(p["label"])
            w.toggled.connect(lambda v: b.setValue(name, v))
        elif kind == "choice":
            w = QtWidgets.QComboBox()
            for o, label in zip(p["options"], p["optionLabels"]):
                w.addItem(label, o)
            w.activated.connect(lambda i: b.setValue(name, w.itemData(i)))
        elif kind == "int":
            w = QtWidgets.QSpinBox()
            w.setRange(int(p["min"]), int(p["max"]))
            w.setSingleStep(max(1, int(p["step"])))
            w.valueChanged.connect(lambda v: b.setValue(name, v))
        elif kind == "number":
            w = QtWidgets.QDoubleSpinBox()
            w.setRange(p["min"], p["max"])
            w.setDecimals(p["decimals"])
            w.setSingleStep(p["step"])
            w.setSuffix(" " + p["unit"] if p["unit"] else "")
            w.valueChanged.connect(lambda v: b.setValue(name, v))
        elif kind == "color":
            w = QtWidgets.QPushButton()
            w.clicked.connect(lambda: b.pickColor(name))
        elif kind == "vector":
            w = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            w.spins = []
            for _i in range(3):
                s = QtWidgets.QDoubleSpinBox()
                s.setRange(-1e7, 1e7)
                s.setDecimals(p["decimals"])
                s.editingFinished.connect(lambda: b.setValue(name, [x.value() for x in w.spins]))
                h.addWidget(s)
                w.spins.append(s)
        elif kind in ("text", "path"):
            w = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            w.edit = QtWidgets.QLineEdit()
            w.edit.setPlaceholderText(p["placeholder"])
            w.edit.textEdited.connect(lambda t: b.setValue(name, t))
            h.addWidget(w.edit, 1)
            if kind == "path":
                browse = QtWidgets.QPushButton(tr("Browse…"))
                browse.clicked.connect(lambda: b.browse(name))
                h.addWidget(browse)
        elif kind == "list":
            w = QtWidgets.QTreeWidget()
            w.setHeaderLabels(p["columns"])
            w.setRootIsDecorated(False)
            w.row_items = {}
            for r in p["rows"]:
                it = QtWidgets.QTreeWidgetItem([str(c) for c in r["cells"]])
                if r.get("enabled", True):
                    it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
                    it.setCheckState(0, QtCore.Qt.Unchecked)
                else:
                    it.setFlags(it.flags() & ~QtCore.Qt.ItemIsUserCheckable)
                w.addTopLevelItem(it)
                w.row_items[r["id"]] = it
            for i in range(len(p["columns"])):
                w.resizeColumnToContents(i)

            def item_changed(it, col):
                if col != 0:
                    return
                for rid, item in w.row_items.items():
                    if item is it:
                        b.setRowChecked(name, rid, it.checkState(0) == QtCore.Qt.Checked)
            w.itemChanged.connect(item_changed)
        else:                                       # note
            w = QtWidgets.QLabel()
            w.setWordWrap(True)
        return w

    def sync(self):
        values, hidden = self.bridge.values, self.bridge.hidden
        for name, (p, w) in self.editors.items():
            v = values.get(name)
            kind = p["kind"]
            w.blockSignals(True)
            try:
                if kind == "bool":
                    w.setChecked(bool(v))
                elif kind == "choice":
                    w.setCurrentIndex(max(0, w.findData(v)))
                elif kind in ("int", "number"):
                    w.setValue(v)
                elif kind == "color":
                    w.setStyleSheet("background: %s;" % v)
                elif kind == "vector":
                    for s, x in zip(w.spins, v):
                        s.blockSignals(True)
                        s.setValue(x)
                        s.blockSignals(False)
                elif kind in ("text", "path"):
                    if w.edit.text() != v:
                        w.edit.setText(v)
                elif kind == "list":
                    for rid, it in w.row_items.items():
                        if it.flags() & QtCore.Qt.ItemIsUserCheckable:
                            it.setCheckState(0, QtCore.Qt.Checked if rid in v
                                             else QtCore.Qt.Unchecked)
                else:
                    w.setText(str(v))
            finally:
                w.blockSignals(False)
            w.setVisible(name not in hidden)

    def sync_state(self):
        self.hint.setText(self.bridge.hint)
        self.hint.setVisible(bool(self.bridge.hint))
        self.err.setText(self.bridge.error)
        self.err.setVisible(bool(self.bridge.error))


# ----------------------------------------------------------------------
#  Dialog hosting the QML panel or the widgets
# ----------------------------------------------------------------------
def _qml_form(bridge, parent):
    try:
        view = qml_host.make_view("GenericPanel.qml", {"bridge": bridge, "i18n": I18n(bridge)},
                                  parent=parent, clear_color=bridge.theme["window"])
    except Exception as exc:
        App.Console.PrintWarning("Assembly Companion: QML panel unavailable, widgets used "
                                 "(%s)\n" % exc)
        return None
    # The bridge must outlive the QML scene (ShowRoom): as a child of the
    # view it is destroyed after the root item.
    bridge.setParent(view)
    view.setMinimumHeight(200)
    return view


class PanelDialog(QtWidgets.QDialog):
    """A model shown as a dialog: QML when wanted and possible, else the
    WidgetForm. exec() returns True when the accept action succeeded; the
    model keeps what it did in model.result."""

    def __init__(self, model, parent=None, qml=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle(model.title)
        self.bridge = Bridge(model)
        lay = QtWidgets.QVBoxLayout(self)
        use = qml_host.use_qml() if qml is None else (qml and qml_host.quick_usable())
        self.form = _qml_form(self.bridge, self) if use else None
        self.is_qml = self.form is not None
        if self.is_qml:
            lay.setContentsMargins(0, 0, 0, 0)
        else:
            self.form = WidgetForm(self.bridge, self)
            self.bridge.setParent(self.form)
        lay.addWidget(self.form)
        self.bridge.closeRequested.connect(lambda ok: self.accept() if ok else self.reject())
        height = model.height or (480 if self.is_qml else self.sizeHint().height())
        self.resize(model.width, height)

    def run(self):
        run = getattr(self, "exec", None) or self.exec_
        return bool(run())


def show_panel(model, parent=None):
    """Show `model` in a modal dialog; True when accepted."""
    if parent is None:
        try:
            import FreeCADGui as Gui
            parent = Gui.getMainWindow()
        except Exception:
            parent = None
    return PanelDialog(model, parent).run()
