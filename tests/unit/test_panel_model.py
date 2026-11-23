# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Panel models without a GUI: values, kinds, list rows, actions, errors."""

import pytest

from freecad.assembly_companion import panel_model as pm

pytestmark = pytest.mark.unit


class Demo(pm.PanelModel):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.add(pm.Param("n", "N", "number", 1.5, min=0, max=10))
        self.add(pm.Param("i", "I", "int", 3, min=1, max=6))
        self.add(pm.Param("b", "B", "bool"))
        self.add(pm.Param("c", "C", "choice", options=[("a", "A"), ("b", "B")]))
        self.add(pm.Param("v", "V", "vector"))
        self.add(pm.Param("t", "T", "text", "x", section="More"))
        self.add(pm.Param("p", "P", "path", section="More"))
        self.add(pm.Param("col", "Col", "color", "#ff0000", section="More"))
        self.add(pm.Param("note", "Hello", "note", section="More"))
        self.add(pm.Param("rows", kind="list", columns=["Name"], section="List", rows=[
            {"id": "r1", "cells": ["one"], "checked": True},
            {"id": "r2", "cells": ["two"]},
            {"id": "r3", "cells": ["three"], "checked": True, "enabled": False}]))
        self.action(pm.Action("apply", "Apply"))
        self.action(pm.Action("ok", "OK", primary=True, accept=True))

    def changed(self, name):
        if name == "t":
            self.values["note"] = "text is " + self.values["t"]

    def trigger(self, name):
        if name == "ok" and not self.values["b"]:
            raise RuntimeError("check B first")
        self.calls.append(name)
        self.result = name


def test_defaults_and_sections():
    m = Demo()
    assert m.get("c") == "a" and m.get("note") == "Hello" and m.get("v") == [0.0, 0.0, 0.0]
    assert m.get("rows") == ["r1"]                  # disabled rows never count
    secs = m.sections()
    assert [s["title"] for s in secs] == ["", "More", "List"]
    assert [p["name"] for p in secs[0]["params"]] == ["n", "i", "b", "c", "v"]
    assert all(set(p) >= {"name", "label", "kind", "options", "rows"} for s in secs
               for p in s["params"])


def test_coercion_and_clamping():
    m = Demo()
    assert m.set("n", "12.5") and m.get("n") == 10
    assert m.set("i", 2.6) and m.get("i") == 3
    assert m.set("i", 0) and m.get("i") == 1
    assert m.set("b", 1) and m.get("b") is True
    assert m.set("v", ["1", 2, 3.5]) and m.get("v") == [1.0, 2.0, 3.5]


def test_invalid_value_sets_error_and_keeps_value():
    m = Demo()
    assert not m.set("c", "zzz")
    assert m.get("c") == "a" and "zzz" in m.error
    assert m.set("c", "b") and m.error == ""
    assert not m.set("v", [1, 2])


def test_changed_hook_updates_other_values():
    m = Demo()
    m.set("t", "abc")
    assert m.get("note") == "text is abc"


def test_list_rows():
    m = Demo()
    m.set_row_checked("rows", "r2", True)
    m.set_row_checked("rows", "r1", False)
    assert m.get("rows") == ["r2"]
    m.set_row_checked("rows", "r3", True)           # disabled: ignored
    assert m.get("rows") == ["r2"]


def test_actions():
    m = Demo()
    assert m.run("apply") is False and m.calls == ["apply"]
    assert m.run("ok") is False and "check B" in m.error   # failed accept keeps the panel
    m.set("b", True)
    assert m.run("ok") is True and m.result == "ok" and m.error == ""
    with pytest.raises(KeyError):
        m.run("nope")


def test_unknown_kind():
    with pytest.raises(ValueError):
        pm.Param("x", kind="slider")
