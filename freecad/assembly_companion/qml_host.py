# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - Qt Quick host
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
qml_host.py (Assembly Companion) - creation of the QQuickWidgets that show
our QML, and the choice between QML and the widgets fallback.

Pitfalls handled here (met by ShowRoom and FreeCAD-Nxt):
  * graphics API: Qt Quick must draw with OpenGL like the 3D view, or the
    panels stay empty on Windows / Qt 6 ("Failed to get a QRhi"). Asked
    before the first QQuickWidget; if it is too late, the widgets are used;
  * imports: FreeCAD's PySide shim has no QtQuick: PySide6 (Qt 6, FreeCAD
    26.x) or PySide2 (Qt 5, FreeCAD 1.0), imported lazily on first use;
  * QML imports are versioned (QtQuick 2.15) to load on Qt 5 and Qt 6;
  * our components use no QML Popup, so the Wayland popup offset of
    offscreen windows (window_offset in Nxt) does not arise;
  * the bridge is parented to the view, so it outlives the QML scene.

quick_usable() is adapted from dtpanels/bridge.py of ShowRoom
(https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later);
make_view() from freecad/nxt/ui/quick_host.py and core/qtquick.py of
FreeCAD-Nxt (https://github.com/obelisk79/FreeCAD-Nxt, LGPL-2.1-or-later).
"""

import os

import FreeCAD as App

try:
    from PySide import QtCore, QtGui
except ImportError:
    from PySide6 import QtCore, QtGui

from . import prefs

QML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "qml")

_quick = {}            # cache: "modules" -> (QtQuickWidgets, QtQuick) or None, "ok" -> bool
forced_off = False     # tests: behave as if Qt Quick were missing


def qml_file(name):
    return os.path.join(QML_DIR, name)


def modules():
    """(QtQuickWidgets, QtQuick) of the running Qt, or None."""
    if "modules" not in _quick:
        mods = None
        for pkg in ("PySide6", "PySide2"):
            try:
                qw = __import__(pkg + ".QtQuickWidgets", fromlist=["QtQuickWidgets"])
                qq = __import__(pkg + ".QtQuick", fromlist=["QtQuick"])
                mods = (qw, qq)
                break
            except Exception:
                continue
        _quick["modules"] = mods
    return _quick["modules"]


def quick_usable():
    """True when Qt Quick can draw with OpenGL here (asked once, before the
    first QQuickWidget)."""
    if forced_off:
        return False
    if "ok" not in _quick:
        os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
        mods = modules()
        ok = mods is not None
        if ok:
            try:
                qq = mods[1]
                api = qq.QSGRendererInterface.GraphicsApi
                if qq.QQuickWindow.graphicsApi() not in (api.OpenGL, api.OpenGLRhi):
                    qq.QQuickWindow.setGraphicsApi(api.OpenGL)
                ok = qq.QQuickWindow.graphicsApi() in (api.OpenGL, api.OpenGLRhi)
            except Exception:
                pass            # Qt 5: always OpenGL
        if not ok:
            App.Console.PrintLog("Assembly Companion: Qt Quick unavailable, widget panels\n")
        _quick["ok"] = ok
    return _quick["ok"]


def use_qml():
    """QML panels wanted (preference) and possible."""
    return bool(prefs.get("UseQmlPanels")) and quick_usable()


class QmlLoadError(RuntimeError):
    """A QML file failed to load; the message lists QML's errors."""


def make_view(source, context, parent=None, clear_color=None):
    """A QQuickWidget showing `source` (file of resources/qml) with the
    context properties `context` ({name: QObject}). Raises QmlLoadError
    with the QML errors when it does not load."""
    qw = modules()[0]
    view = qw.QQuickWidget(parent)
    view.setResizeMode(qw.QQuickWidget.SizeRootObjectToView)
    if clear_color:
        view.setClearColor(QtGui.QColor(clear_color))
    view.engine().addImportPath(QML_DIR)
    warnings = []
    view.engine().warnings.connect(lambda errs: warnings.extend(e.toString() for e in errs))
    ctx = view.rootContext()
    for name, value in context.items():
        ctx.setContextProperty(name, value)
    view.setSource(QtCore.QUrl.fromLocalFile(qml_file(source)))
    if view.status() != qw.QQuickWidget.Ready or warnings:
        detail = "\n".join([e.toString() for e in view.errors()] + warnings)
        view.deleteLater()
        raise QmlLoadError("%s failed to load:\n%s" % (source, detail))
    view.qml_warnings = warnings        # later warnings (bindings), for the tests
    return view
