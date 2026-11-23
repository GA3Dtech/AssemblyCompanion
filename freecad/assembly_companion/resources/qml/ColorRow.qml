// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    id: row
    property var p
    property var th
    implicitHeight: Math.round(30 * th.s)
    width: parent ? parent.width : 0
    RowLabel {
        th: row.th
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        text: p.label
    }
    Rectangle {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(48 * th.s); height: Math.round(22 * th.s); radius: Math.round(4 * th.s)
        color: bridge.values[p.name] || "black"
        border.color: th.line
        MouseArea { anchors.fill: parent; onClicked: bridge.pickColor(p.name) }
    }
}
