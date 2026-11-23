// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

// "list": table of rows with a check box each; the value is the list of
// checked row ids. Rows that are not enabled have no check box.
Item {
    id: row
    property var p
    property var th
    property var checked: bridge.values[p.name] || []
    property real checkW: Math.round(26 * th.s)
    property real colW: (width - checkW) / Math.max(1, p.columns.length)
    property real rowH: Math.round(24 * th.s)
    implicitHeight: header.height + Math.min(Math.max(p.rows.length, 3), 12) * rowH + 4
    width: parent ? parent.width : 0

    Row {
        id: header
        x: row.checkW
        height: row.rowH
        Repeater {
            model: p.columns
            Text {
                width: row.colW
                height: row.rowH
                verticalAlignment: Text.AlignVCenter
                text: modelData
                color: th.muted
                elide: Text.ElideRight
                font.pixelSize: Math.round(11 * th.s); font.family: th.family; font.bold: true
            }
        }
    }
    ListView {
        id: list
        objectName: "list_" + p.name
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        width: parent.width
        clip: true
        model: p.rows
        delegate: Rectangle {
            width: list.width
            height: row.rowH
            color: index % 2 ? th.card : th.window
            property bool on: row.checked.indexOf(modelData.id) >= 0
            property bool enabled_: modelData.enabled !== false
            Rectangle {
                visible: parent.enabled_
                x: Math.round(5 * th.s)
                anchors.verticalCenter: parent.verticalCenter
                width: Math.round(16 * th.s); height: width; radius: 3
                color: parent.on ? th.accent : th.field
                border.color: th.line
                Text { anchors.centerIn: parent; text: "✓"; visible: parent.parent.on; color: th.accentText; font.pixelSize: Math.round(11 * th.s) }
            }
            Row {
                x: row.checkW
                height: parent.height
                Repeater {
                    model: modelData.cells
                    Text {
                        width: row.colW
                        height: row.rowH
                        verticalAlignment: Text.AlignVCenter
                        text: String(modelData)
                        color: th.text
                        elide: Text.ElideRight
                        font.pixelSize: Math.round(12 * th.s); font.family: th.family
                    }
                }
            }
            MouseArea {
                anchors.fill: parent
                enabled: parent.enabled_
                onClicked: bridge.setRowChecked(p.name, modelData.id, !parent.on)
            }
        }
    }
}
