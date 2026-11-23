# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Model of the "New part from selection" panel: name preview, next free
number, linked binder hides the insertion, OK calls the API once."""

import os

import pytest

pytestmark = pytest.mark.unit


class _Obj(object):
    def __init__(self, name):
        self.Name = name


@pytest.fixture
def panel(tmp_path, monkeypatch):
    try:
        from freecad.assembly_companion import api, new_part, prefs
    except ImportError as exc:
        pytest.skip("new_part.py does not import here: %s" % exc)
    for name in ("AB_001a_Old.FCStd", "AB_002a_Other.FCStd"):
        (tmp_path / name).touch()
    saved = {k: prefs.get(k) for k in ("NewPartLastDir", "NewPartLastPrefix", "NewPartDir",
                                       "NewPartPrefix", "NewPartBinderMode", "NewPartInsert")}
    prefs.put("NewPartLastDir", str(tmp_path))
    prefs.put("NewPartLastPrefix", "AB")
    prefs.put("NewPartBinderMode", "copy")
    prefs.put("NewPartInsert", True)
    calls = []

    def fake(doc, selection, path, label=None, linked=False, insert=True):
        calls.append((selection, path, label, linked, insert))
        return {"path": path, "document": "New", "body": "Body", "binder": "Binder",
                "inserted": None}
    monkeypatch.setattr(api, "new_part_from_selection", fake)
    m = new_part.NewPartPanel(None, [(_Obj("Assembly"), "Plate.Face6")])
    yield m, calls, str(tmp_path)
    for k, v in saved.items():
        prefs.put(k, v)


def test_next_free_number_and_preview(panel):
    m, _calls, folder = panel
    assert m.get("number") == 3
    m.set("description", "Cover")
    assert m.get("preview") == "AB_003a_Cover.FCStd"
    assert m.path() == os.path.join(folder, "AB_003a_Cover.FCStd")
    m.set("prefix", "CD")
    assert m.get("number") == 1


def test_existing_file_and_missing_folder_are_reported(panel):
    m, calls, folder = panel
    m.set("number", 1)
    m.set("description", "Old")
    assert "already exists" in m.get("preview")
    assert m.run("create") is False and "already exists" in m.error and calls == []
    m.set("folder", os.path.join(folder, "nope"))
    assert "does not exist" in m.get("preview")


def test_linked_hides_insert(panel):
    m, _calls, _folder = panel
    m.set("mode", "linked")
    assert "insert" in m.hidden and m.get("insert") is False
    m.set("mode", "copy")
    assert "insert" not in m.hidden


def test_create_calls_api_once(panel):
    m, calls, folder = panel
    m.set("description", "My cover")
    assert m.run("create") is True
    assert calls == [([["Assembly", "Plate.Face6"]],
                      os.path.join(folder, "AB_003a_My cover.FCStd"), "My cover", False, True)]
    assert m.result["body"] == "Body"
