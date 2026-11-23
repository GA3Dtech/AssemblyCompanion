# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Model of the "Frozen parts up to date?" panel, with a fake API."""

import pytest

pytestmark = pytest.mark.unit

ROWS = [
    {"name": "Copy1", "label": "Plate", "state": "outdated", "source_file": "/a/plate.FCStd",
     "frozen": "2026-01-01T10:00:00", "source_saved": "2026-02-01T10:00:00"},
    {"name": "Copy2", "label": "Pin", "state": "ok", "source_file": "/a/pin.FCStd",
     "frozen": "2026-01-01T10:00:00", "source_saved": "2025-12-01T10:00:00"},
    {"name": "Copy3", "label": "Gone", "state": "missing", "source_file": "/a/gone.FCStd",
     "frozen": "2026-01-01T10:00:00", "source_saved": None},
]


@pytest.fixture
def panel(monkeypatch):
    try:
        from freecad.assembly_companion import api, outdated
    except ImportError as exc:                     # Part stand-in too thin
        pytest.skip("outdated.py does not import here: %s" % exc)
    calls = []
    monkeypatch.setattr(api, "outdated_parts", lambda doc: ROWS)
    monkeypatch.setattr(api, "refreeze_outdated",
                        lambda doc, names=None, dry_run=False:
                        calls.append(list(names)) or {"refrozen": list(names)})
    return outdated.OutdatedPanel("Doc"), calls


def test_rows_checked_and_enabled(panel):
    m, _calls = panel
    p = m.param("parts")
    assert [r["id"] for r in p.rows] == ["Copy1", "Copy2", "Copy3"]
    assert m.get("parts") == ["Copy1"]                         # outdated ones checked
    assert [r["enabled"] for r in p.rows] == [True, True, False]
    assert p.rows[0]["cells"][2] == "2026-01-01 10:00" and p.rows[2]["cells"][3] == "—"
    assert [a.name for a in m.actions] == ["refreeze"]


def test_accept_calls_api_once_with_checked(panel):
    m, calls = panel
    m.set_row_checked("parts", "Copy2", True)
    assert m.run("refreeze") is True
    assert calls == [["Copy1", "Copy2"]] and m.result == ["Copy1", "Copy2"]


def test_nothing_checked_closes_without_api_call(panel):
    m, calls = panel
    m.set_row_checked("parts", "Copy1", False)
    assert m.run("refreeze") is True and calls == [] and m.result == []
