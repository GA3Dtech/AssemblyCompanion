// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

// "vector": three fields x, y, z.
Item {
    id: row
    property var p
    property var th
    property var value: bridge.values[p.name] || [0, 0, 0]
    implicitHeight: Math.round(30 * th.s)
    width: parent ? parent.width : 0
    function commit(i, v) {
        if (isNaN(v)) return
        var out = [row.value[0], row.value[1], row.value[2]]
        out[i] = v
        bridge.setValue(p.name, out)
    }
    RowLabel {
        th: row.th
        anchors.left: parent.left
        anchors.right: fields.left
        anchors.verticalCenter: parent.verticalCenter
        text: p.label
    }
    Row {
        id: fields
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4
        Repeater {
            model: 3
            Rectangle {
                width: Math.round(70 * th.s); height: Math.round(24 * th.s); radius: Math.round(4 * th.s)
                color: th.field
                TextInput {
                    anchors.fill: parent
                    anchors.margins: 4
                    horizontalAlignment: TextInput.AlignRight
                    verticalAlignment: TextInput.AlignVCenter
                    color: th.text
                    font.pixelSize: Math.round(12 * th.s); font.family: th.family
                    selectByMouse: true
                    clip: true
                    text: Number(row.value[index]).toFixed(p.decimals)
                    onEditingFinished: row.commit(index, parseFloat(text.replace(",", ".")))
                }
            }
        }
    }
}
