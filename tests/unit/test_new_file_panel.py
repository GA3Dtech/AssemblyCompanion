# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Model of the "New file" panel: naming like the new parts, container and
Body named after the description until edited, options, one API call."""

import os

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def panel(tmp_path, monkeypatch):
    from freecad.assembly_companion import api, new_file, prefs
    (tmp_path / "AB_004a_Old.FCStd").touch()
    saved = {k: prefs.get(k) for k in ("NewPartLastDir", "NewPartLastPrefix")}
    prefs.put("NewPartLastDir", str(tmp_path))
    prefs.put("NewPartLastPrefix", "AB")
    calls = []
    monkeypatch.setattr(api, "new_file", lambda path, part=None, body=None: calls.append(
        (path, part, body)) or {"path": path, "document": "D", "part": part, "body": body})
    yield new_file.NewFilePanel(None), calls, str(tmp_path)
    for k, v in saved.items():
        prefs.put(k, v)


def test_naming_and_names_follow_the_description(panel):
    m, _calls, folder = panel
    assert m.get("number") == 5
    m.set("description", "Bracket")
    assert m.get("preview") == "AB_005a_Bracket.FCStd"
    assert m.get("part_label") == "Bracket" and m.get("body_label") == "Bracket"
    m.set("body_label", "Main body")                # edited: no longer follows
    m.set("description", "Bracket v2")
    assert m.get("part_label") == "Bracket v2" and m.get("body_label") == "Main body"


def test_options_hide_the_names(panel):
    m, _calls, _folder = panel
    m.set("with_part", False)
    assert "part_label" in m.hidden
    m.set("with_body", False)
    assert "body_label" in m.hidden
    m.set("with_part", True)
    assert "part_label" not in m.hidden


def test_create_calls_the_api_once(panel):
    m, calls, folder = panel
    m.set("description", "Bracket")
    m.set("with_body", False)
    assert m.run("create") is True
    assert calls == [(os.path.join(folder, "AB_005a_Bracket.FCStd"), "Bracket", None)]


def test_existing_file_refused(panel):
    m, calls, _folder = panel
    m.set("number", 4)
    m.set("description", "Old")
    assert m.run("create") is False and "already exists" in m.error and calls == []
