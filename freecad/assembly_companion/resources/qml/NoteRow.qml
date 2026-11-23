// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    property var p
    property var th
    implicitHeight: t.implicitHeight + 6
    width: parent ? parent.width : 0
    Text {
        id: t
        width: parent.width
        text: { var v = bridge.values[p.name]; return v === undefined ? p.label : String(v) }
        color: th.text
        wrapMode: Text.WordWrap
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
    }
}
