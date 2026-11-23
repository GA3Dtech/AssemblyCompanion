// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

// "text" and "path" (with a Browse button opening the native file dialog).
Item {
    id: row
    property var p
    property var th
    property string value: { var v = bridge.values[p.name]; return v === undefined ? "" : String(v) }
    onValueChanged: if (!input.activeFocus && input.text !== value) input.text = value
    Component.onCompleted: input.text = value
    implicitHeight: Math.round(30 * th.s)
    width: parent ? parent.width : 0
    RowLabel {
        id: lab
        th: row.th
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(row.width * 0.28)
        text: p.label
    }
    Rectangle {
        id: field
        anchors.left: lab.right
        anchors.leftMargin: 8
        anchors.right: browse.visible ? browse.left : parent.right
        anchors.rightMargin: browse.visible ? 6 : 0
        anchors.verticalCenter: parent.verticalCenter
        height: Math.round(24 * th.s)
        radius: Math.round(4 * th.s)
        color: th.field
        border.width: input.activeFocus ? 1 : 0
        border.color: th.accent
        TextInput {
            id: input
            objectName: "input_" + p.name
            anchors.fill: parent
            anchors.leftMargin: 6; anchors.rightMargin: 6
            verticalAlignment: TextInput.AlignVCenter
            color: th.text
            selectionColor: th.accent
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
            selectByMouse: true
            clip: true
            onTextEdited: bridge.setValue(p.name, text)
        }
        Text {
            anchors.fill: input
            verticalAlignment: Text.AlignVCenter
            visible: input.text.length === 0
            text: p.placeholder
            color: th.muted
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
    }
    PillButton {
        id: browse
        th: row.th
        visible: p.kind === "path"
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        label: i18n.tr("Browse…")
        onClicked: bridge.browse(p.name)
    }
}
