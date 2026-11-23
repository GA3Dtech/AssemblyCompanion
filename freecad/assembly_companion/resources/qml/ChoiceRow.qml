// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

// "choice": one pill per option (no Popup: nothing to place under Wayland).
Item {
    id: row
    property var p
    property var th
    property string value: { var v = bridge.values[p.name]; return v === undefined ? "" : v }
    implicitHeight: col.implicitHeight + 6
    width: parent ? parent.width : 0
    Column {
        id: col
        width: parent.width
        spacing: 4
        RowLabel { th: row.th; width: parent.width; text: p.label }
        Flow {
            width: parent.width
            spacing: 4
            Repeater {
                model: p.options
                Rectangle {
                    property bool sel: modelData === row.value
                    width: lab.implicitWidth + Math.round(16 * th.s)
                    height: Math.round(24 * th.s); radius: Math.round(6 * th.s)
                    color: sel ? th.accent : th.field
                    Text { id: lab; anchors.centerIn: parent; text: p.optionLabels[index]; color: parent.sel ? th.accentText : th.text; font.pixelSize: Math.round(11 * th.s); font.family: th.family; font.bold: parent.sel }
                    MouseArea { anchors.fill: parent; onClicked: bridge.setValue(p.name, modelData) }
                }
            }
        }
    }
}
