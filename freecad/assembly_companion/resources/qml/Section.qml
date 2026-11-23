// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

// One section: optional title and its parameter rows (one component per kind).
Rectangle {
    id: sec
    property var th
    property var section
    height: body.implicitHeight + Math.round(16 * th.s)
    radius: Math.round(6 * th.s)
    color: th.card

    Column {
        id: body
        x: Math.round(10 * th.s); y: Math.round(8 * th.s)
        width: parent.width - 2 * x
        spacing: Math.round(4 * th.s)
        Text {
            visible: sec.section.title.length > 0
            text: sec.section.title
            color: sec.th.muted
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
            font.bold: true
        }
        Repeater {
            model: sec.section.params
            Loader {
                width: body.width
                property bool hiddenRow: bridge.hidden.indexOf(modelData.name) >= 0
                visible: !hiddenRow
                height: hiddenRow ? 0 : (item ? item.implicitHeight : 0)
                Component.onCompleted: setSource(
                    modelData.kind === "bool" ? "ToggleRow.qml"
                    : modelData.kind === "choice" ? "ChoiceRow.qml"
                    : modelData.kind === "int" || modelData.kind === "number" ? "NumberRow.qml"
                    : modelData.kind === "color" ? "ColorRow.qml"
                    : modelData.kind === "vector" ? "VectorRow.qml"
                    : modelData.kind === "path" || modelData.kind === "text" ? "TextRow.qml"
                    : modelData.kind === "list" ? "ListRow.qml" : "NoteRow.qml",
                    { "p": modelData, "th": sec.th })
            }
        }
    }
}
