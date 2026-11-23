// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

// "number" and "int": a field; up / down arrows step the value.
Item {
    id: row
    property var p
    property var th
    property real value: { var v = bridge.values[p.name]; return v === undefined ? 0 : v }
    implicitHeight: Math.round(30 * th.s)
    width: parent ? parent.width : 0
    function fmt(v) { return p.kind === "int" ? String(Math.round(v)) : Number(v).toFixed(p.decimals) }
    function commit(v) { if (!isNaN(v)) bridge.setValue(p.name, v) }
    RowLabel {
        th: row.th
        anchors.left: parent.left
        anchors.right: field.left
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        text: p.label
    }
    Rectangle {
        id: field
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(110 * th.s); height: Math.round(24 * th.s)
        radius: Math.round(4 * th.s)
        color: th.field
        border.width: input.activeFocus ? 1 : 0
        border.color: th.accent
        TextInput {
            id: input
            objectName: "input_" + p.name
            anchors.left: parent.left
            anchors.right: unit.left
            anchors.margins: 6
            anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: TextInput.AlignRight
            color: th.text
            selectionColor: th.accent
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
            selectByMouse: true
            clip: true
            text: row.fmt(row.value)
            onEditingFinished: { row.commit(parseFloat(text.replace(",", "."))); text = Qt.binding(function() { return row.fmt(row.value) }) }
            Keys.onUpPressed: row.commit(row.value + p.step)
            Keys.onDownPressed: row.commit(row.value - p.step)
        }
        Text {
            id: unit
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: p.unit
            color: th.muted
            font.pixelSize: Math.round(11 * th.s); font.family: th.family
        }
    }
}
