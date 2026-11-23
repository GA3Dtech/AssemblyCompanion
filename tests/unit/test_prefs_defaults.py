# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Every preference key used in the code exists in prefs.DEFAULTS."""

import os
import re

import pytest

from freecad.assembly_companion import prefs

pytestmark = pytest.mark.unit

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__)))), "freecad", "assembly_companion")


def _keys_used():
    used = {}
    for name in os.listdir(PKG):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(PKG, name), encoding="utf-8").read()
        for m in re.finditer(r"prefs\.(?:get|put)\(\s*[\"']([A-Za-z]\w*)[\"']", text):
            used.setdefault(m.group(1), name)
        if name == "prefs.py":
            for m in re.finditer(r"\b(?:get|put)\(\s*[\"']([A-Za-z]\w*)[\"']", text):
                used.setdefault(m.group(1), name)
    return used


def test_every_used_key_has_a_default():
    missing = {k: f for k, f in _keys_used().items() if k not in prefs.DEFAULTS}
    assert not missing


def test_get_returns_the_default_type():
    for key, default in prefs.DEFAULTS.items():
        assert isinstance(prefs.get(key), type(default)), key
