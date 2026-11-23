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
    property bool value: bridge.values[p.name] === true
    implicitHeight: Math.round(30 * th.s)
    width: parent ? parent.width : 0
    RowLabel {
        th: row.th
        anchors.left: parent.left
        anchors.right: sw.left
        anchors.verticalCenter: parent.verticalCenter
        text: p.label
    }
    Rectangle {
        id: sw
        objectName: "toggle_" + p.name
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(38 * th.s); height: Math.round(20 * th.s); radius: Math.round(10 * th.s)
        color: row.value ? th.accent : th.line
        Rectangle {
            x: row.value ? parent.width - width - 2 : 2
            anchors.verticalCenter: parent.verticalCenter
            width: Math.round(16 * th.s); height: width; radius: width / 2
            color: "white"
        }
        MouseArea { anchors.fill: parent; anchors.margins: -4; onClicked: bridge.setValue(p.name, !row.value) }
    }
}
