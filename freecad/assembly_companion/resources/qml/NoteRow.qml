// SPDX-License-Identifier: LGPL-2.1-or-later
// Assembly Companion - generic panel component (see bridge.py).
// Layout and look adapted from dtpanels/qml of ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, LGPL-2.1-or-later).
// Versioned imports: loads on Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    property var p
    property var th
    id: row
    // a note whose text differs from its label shows the label in front (e.g. "File:")
    property string value: { var v = bridge.values[p.name]; return v === undefined ? p.label : String(v) }
    property bool labelled: p.label.length > 0 && value !== p.label
    implicitHeight: t.implicitHeight + 6
    width: parent ? parent.width : 0
    RowLabel {
        id: lab
        th: row.th
        visible: row.labelled
        width: row.labelled ? Math.round(row.width * 0.28) : 0
        text: p.label
    }
    Text {
        id: t
        x: lab.width
        width: parent.width - x
        text: row.value
        color: th.text
        wrapMode: Text.WordWrap
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
    }
}
