// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Rectangle {
    id: btn
    property var th
    property string label
    property bool primary: false
    signal clicked()
    width: txt.implicitWidth + Math.round(22 * th.s)
    height: Math.round(28 * th.s)
    radius: Math.round(4 * th.s)
    color: primary && !m.pressed ? th.accent : (m.pressed ? th.line : th.field)
    border.width: primary ? 0 : 1
    border.color: th.line
    Text {
        id: txt
        anchors.centerIn: parent
        text: btn.label
        color: btn.primary ? btn.th.accentText : btn.th.text
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
        font.bold: btn.primary
    }
    MouseArea { id: m; anchors.fill: parent; onClicked: btn.clicked() }
}
