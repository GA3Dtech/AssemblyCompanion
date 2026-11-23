# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Files made by version 0.1.0 still open and work with the current code."""

import os
import shutil

import pytest

from conftest import open_doc

pytestmark = pytest.mark.freecad

LEGACY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "fixtures", "legacy")
STATES = sorted(os.path.join(v, s) for v in (os.listdir(LEGACY) if os.path.isdir(LEGACY) else [])
                if os.path.isdir(os.path.join(LEGACY, v))
                for s in os.listdir(os.path.join(LEGACY, v))
                if os.path.isfile(os.path.join(LEGACY, v, s, "assembly.FCStd")))


def _api():
    from freecad.assembly_companion import api
    return api


@pytest.fixture
def legacy_copy(tmp_path):
    def _copy(rel):
        dst = str(tmp_path / rel.replace(os.sep, "_"))
        shutil.copytree(os.path.join(LEGACY, rel), dst)
        return dst
    return _copy


@pytest.mark.parametrize("rel", STATES)
def test_legacy_opens_clean(legacy_copy, rel):
    api = _api()
    doc = open_doc(os.path.join(legacy_copy(rel), "assembly.FCStd"))
    assert not [o.Label for o in doc.Objects if "Invalid" in o.State]
    assert api.diagnose(doc)["broken"] == 0


def test_legacy_lightweight_restores(legacy_copy):
    api = _api()
    rel = [s for s in STATES if s.endswith("state_lightweight")][0]
    doc = open_doc(os.path.join(legacy_copy(rel), "assembly.FCStd"))
    r = api.restore_full(doc)
    assert sorted(r["restored"]) == ["Block", "Pin", "Plate"]
    assert api.diagnose(doc)["broken"] == 0


def test_legacy_frozen_relinks_and_refreezes(legacy_copy):
    api = _api()
    rel = [s for s in STATES if s.endswith("state_frozen")][0]
    doc = open_doc(os.path.join(legacy_copy(rel), "assembly.FCStd"))
    assert sorted(api.relink_parts(doc)["relinked"]) == ["Block", "Pin", "Plate"]
    api.freeze_parts(doc)
    assert api.diagnose(doc)["broken"] == 0
