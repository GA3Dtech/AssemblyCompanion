// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

// Generic form panel: hint, error banner, sections of parameter rows, and
// the action buttons. Everything comes from the "bridge" context object.
Rectangle {
    id: root
    property var th: bridge.theme
    color: th.window

    Column {
        id: top
        x: Math.round(10 * th.s); y: Math.round(10 * th.s)
        width: root.width - 2 * x
        spacing: Math.round(8 * th.s)
        Text {
            width: parent.width
            visible: text.length > 0
            text: bridge.hint
            color: th.muted
            wrapMode: Text.WordWrap
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
        Rectangle {
            width: parent.width
            height: errText.implicitHeight + 16
            radius: Math.round(6 * th.s)
            visible: bridge.error.length > 0
            color: Qt.rgba(0.88, 0.35, 0.32, 0.16)
            border.color: th.bad
            Text {
                id: errText
                x: 10; y: 8
                width: parent.width - 20
                text: bridge.error
                color: th.bad
                wrapMode: Text.WordWrap
                font.pixelSize: Math.round(12 * th.s); font.family: th.family
            }
        }
    }

    Flickable {
        id: flick
        anchors.top: top.bottom
        anchors.topMargin: Math.round(8 * th.s)
        anchors.bottom: buttons.top
        anchors.bottomMargin: Math.round(8 * th.s)
        x: top.x
        width: top.width
        clip: true
        contentHeight: col.implicitHeight
        Column {
            id: col
            width: flick.width
            spacing: Math.round(8 * th.s)
            Repeater {
                model: bridge.sections
                Section { th: root.th; section: modelData; width: col.width }
            }
        }
    }

    Row {
        id: buttons
        objectName: "buttons"
        anchors.right: parent.right
        anchors.rightMargin: top.x
        anchors.bottom: parent.bottom
        anchors.bottomMargin: top.x
        spacing: Math.round(6 * th.s)
        Repeater {
            model: bridge.actions
            PillButton {
                th: root.th
                label: modelData.label
                primary: modelData.primary === true
                onClicked: bridge.trigger(modelData.name)
            }
        }
        PillButton {
            th: root.th
            objectName: "cancel"
            label: bridge.cancelLabel
            onClicked: bridge.trigger("__cancel__")
        }
    }
}
