# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - panel models (no GUI)
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
panel_model.py (Assembly Companion) - description of a form panel as data:
typed parameters grouped in sections, actions, title. One model drives both
interfaces, built by bridge.py: the QML panel and the classic widgets
fallback. A panel is never written twice by hand; when the engine cannot
show something, the engine gets a new parameter kind.

The idea and the parameter dicts follow dtpanels/models.py and
dtpanels/bridge.py of ShowRoom (https://github.com/oficinerobotica/ShowRoom,
LGPL-2.1-or-later), rewritten for dialogs whose model calls api.py.

Rules:
  * no Qt here: models are tested without a GUI;
  * no business logic in the QML, the widgets or the bridge: actions of the
    model call api.py;
  * the model does not touch the document while the panel is open; the
    accept action makes ONE api call (one undo step), Cancel changes nothing.

Parameter kinds:
  number, int, bool, choice, color, vector, path, text, list, note
A "list" is a table of rows with check boxes: its value is the list of the
checked row ids; rows are {"id", "cells": [...], "checked", "enabled"}.
With checkable=False it has no check boxes and a click on a row calls
row_clicked(name, row_id) (e.g. select the objects of that row).
"""

KINDS = ("number", "int", "bool", "choice", "color", "vector", "path", "text", "list",
         "note")


class Param(object):
    """One edited value. `options` (choice) is a list of (value, label);
    `columns` (list) the column titles; `mode` (path) is "dir", "open" or
    "save" with a `filter` such as "CSV files (*.csv)"."""

    def __init__(self, name, label="", kind="text", default=None, section="", tip="",
                 min=0.0, max=100.0, step=1.0, decimals=2, unit="", options=(),
                 columns=(), rows=(), mode="dir", filter="", placeholder="", checkable=True):
        if kind not in KINDS:
            raise ValueError("unknown parameter kind: %s" % kind)
        self.name, self.label, self.kind = name, label, kind
        self.section, self.tip = section, tip
        self.min, self.max, self.step, self.decimals, self.unit = min, max, step, decimals, unit
        self.options = [tuple(o) for o in options]
        self.columns = list(columns)
        self.rows = [dict(r) for r in rows]
        self.mode, self.filter, self.placeholder = mode, filter, placeholder
        self.checkable = checkable
        if default is None:
            default = self._empty()
        self.default = default

    def _empty(self):
        return {"number": 0.0, "int": 0, "bool": False, "color": "#000000",
                "vector": [0.0, 0.0, 0.0], "list": None, "note": self.label,
                "choice": self.options[0][0] if self.options else ""}.get(self.kind, "")

    def coerce(self, value):
        """Value converted to the kind (and clamped); raises ValueError."""
        k = self.kind
        if k == "number":
            return min(max(float(value), self.min), self.max)
        if k == "int":
            return int(min(max(int(round(float(value))), self.min), self.max))
        if k == "bool":
            return bool(value)
        if k == "choice":
            if value not in [o[0] for o in self.options]:
                raise ValueError("%r is not an option of %s" % (value, self.name))
            return value
        if k == "vector":
            v = [float(x) for x in value]
            if len(v) != 3:
                raise ValueError("a vector has 3 components")
            return v
        if k == "list":
            ids = [r["id"] for r in self.rows if r.get("enabled", True)]
            return [i for i in ids if i in list(value)]
        return "" if value is None else str(value)

    def public(self):
        """What the interfaces see (plain data, no callables)."""
        return {"name": self.name, "label": self.label, "kind": self.kind, "tip": self.tip,
                "min": float(self.min), "max": float(self.max), "step": float(self.step),
                "decimals": int(self.decimals), "unit": self.unit,
                "options": [o[0] for o in self.options],
                "optionLabels": [o[1] for o in self.options],
                "columns": list(self.columns), "rows": [dict(r) for r in self.rows],
                "mode": self.mode, "filter": self.filter, "placeholder": self.placeholder,
                "checkable": self.checkable}


class Action(object):
    """A button. `accept`: the panel's main action (OK); it closes the panel
    when it succeeds. Other actions run and leave the panel open."""

    def __init__(self, name, label, primary=False, accept=False, tip=""):
        self.name, self.label, self.primary, self.accept, self.tip = \
            name, label, primary, accept, tip

    def public(self):
        return {"name": self.name, "label": self.label, "primary": self.primary,
                "accept": self.accept, "tip": self.tip}


class PanelModel(object):
    """Base class of the panel models. Subclasses fill `params` and
    `actions` and implement trigger(name) (and changed(name) to react to an
    edit, e.g. update a note or another value)."""

    title = ""
    hint = ""
    cancel_label = ""            # "" = the standard Cancel / Close text
    width = 560
    height = 0                   # 0 = fit the content

    def __init__(self):
        self.params = []
        self.actions = []
        self.values = {}
        self.hidden = set()
        self.error = ""
        self.result = None       # set by the accept action

    # --- building ------------------------------------------------------
    def add(self, param):
        self.params.append(param)
        if param.kind == "list" and param.default is None:
            value = [r["id"] for r in param.rows if r.get("checked") and r.get("enabled", True)]
        else:
            value = param.default
        self.values[param.name] = value
        return param

    def action(self, act):
        self.actions.append(act)
        return act

    def param(self, name):
        for p in self.params:
            if p.name == name:
                return p
        raise KeyError(name)

    def sections(self):
        """[{"title", "params": [public dicts]}] in the order of the params."""
        out, index = [], {}
        for p in self.params:
            if p.section not in index:
                index[p.section] = {"title": p.section, "params": []}
                out.append(index[p.section])
            index[p.section]["params"].append(p.public())
        return out

    # --- editing (called by the bridge) --------------------------------
    def get(self, name):
        return self.values[name]

    def set(self, name, value):
        """Set a value (converted to its kind); the model may react in
        changed(). Errors are kept in self.error for the interface."""
        p = self.param(name)
        try:
            self.values[name] = p.coerce(value)
            self.error = ""
            self.changed(name)
        except Exception as exc:
            self.error = str(exc)
            return False
        return True

    def set_row_checked(self, name, row_id, checked):
        cur = [i for i in self.values[name] if i != row_id]
        if checked:
            cur.append(row_id)
        return self.set(name, cur)

    def run(self, name):
        """Run an action. Returns True when the panel must close (accept
        action that succeeded)."""
        act = [a for a in self.actions if a.name == name]
        if not act:
            raise KeyError(name)
        try:
            self.trigger(name)
            self.error = ""
        except Exception as exc:
            self.error = str(exc)
            return False
        return act[0].accept

    # --- to override ---------------------------------------------------
    def changed(self, name):
        pass

    def row_clicked(self, name, row_id):
        """A row of a non-checkable list was clicked."""

    def trigger(self, name):
        raise NotImplementedError(name)

    def browse_start(self, name):
        """Folder or file where the native file dialog of a path opens."""
        return self.values.get(name, "")
