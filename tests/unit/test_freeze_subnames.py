# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Subname handling of freeze.py (pure string logic)."""

import pytest

from freecad.assembly_companion import freeze

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("sub, expected", [
    ("Link.Pad.;#mapped;.Face6", (["Link", "Pad"], ";#mapped;", "Face6")),
    ("Link.Body.", (["Link", "Body"], "", "")),
    ("Face6", ([], "", "Face6")),
    ("", ([], "", "")),
    ("Asm.Link.Body.Edge12", (["Asm", "Link", "Body"], "", "Edge12")),
    ("Link.Vertex3", (["Link"], "", "Vertex3")),
    ("?Link.?Face2", (["Link"], "", "Face2")),            # '?' missing-element markers
    ("Link.Body.;g12;SKT.Edge4", (["Link", "Body"], ";g12;SKT", "Edge4")),
    ("Link.Face", (["Link", "Face"], "", "")),            # no number: not an element
])
def test_decouper_sub(sub, expected):
    assert freeze.decouper_sub(sub) == expected


@pytest.mark.parametrize("sub, k, remap, expected", [
    ("Asm.Link.Body.Pad.Face6", 1, None, "Asm.Link.Face6"),
    ("Link.Body.;#m;.Face6", 0, None, "Link.Face6"),
    ("Body.Face6", -1, None, "Face6"),                    # reference starts at the Link
    ("Asm.Link.Body.Face6", 1, {"Face6": "Face9"}, "Asm.Link.Face9"),
    ("Asm.Link.Body.Face6", 1, {"Face6": ""}, "Asm.Link.Face6"),   # empty remap ignored
    ("Asm.Link.Body.", 1, None, "Asm.Link."),
])
def test_reecrire_sub(sub, k, remap, expected):
    assert freeze.reecrire_sub(sub, k, remap) == expected


def test_reecrire_sub_chemins_translates_the_path():
    chemins = {"Body001": ("Fige_Body001", None),
               "Sub": ("Fige_Sub", {"Body002": ("Fige_Body002", None)})}
    assert freeze.reecrire_sub_chemins("Link.Body001.Face6", 0, chemins) == \
        "Link.Fige_Body001.Face6"
    assert freeze.reecrire_sub_chemins("Body001.Pad.Face6", -1, chemins) == "Fige_Body001.Face6"
    assert freeze.reecrire_sub_chemins("Link.Sub.Body002.Edge3", 0, chemins) == \
        "Link.Fige_Sub.Fige_Body002.Edge3"


def test_reecrire_sub_chemins_keeps_unknown_names():
    assert freeze.reecrire_sub_chemins("Link.Other.Face1", 0, {"Body": ("X", None)}) == \
        "Link.Other.Face1"
    # empty mapping: every path kept, only the mapped names are dropped
    assert freeze.reecrire_sub_chemins("Link.Body.;#m;.Face1", 0, {}) == "Link.Body.Face1"


@pytest.mark.parametrize("text, element", [
    ("Face6", "Face6"), ("a.Edge12", "Edge12"), ("Vertex3", "Vertex3"),
    ("a.Face", None), ("a.Faces6", None), ("Wire2", None), ("Face6.", None),
])
def test_element_regex(text, element):
    m = freeze._RE_ELEM.search(text)
    assert (m.group(1) if m else None) == element
