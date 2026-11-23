# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Translation tables: complete, same named fields as the English text."""

import json
import os
import string
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRANS = os.path.join(ROOT, "freecad", "assembly_companion", "translations")
LANGS = ("fr", "de", "it", "es")


def _fields(text):
    return sorted((name, spec) for _lit, name, spec, _conv in string.Formatter().parse(text)
                  if name is not None)


def test_tools_i18n_check_is_clean():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "i18n.py"), "check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "missing:" not in r.stdout
    assert "unused" not in r.stdout.replace(" 0 unused", "")


@pytest.mark.parametrize("code", LANGS)
def test_named_fields_match_english(code):
    with open(os.path.join(TRANS, code + ".json"), encoding="utf-8") as fh:
        table = json.load(fh)
    bad = [k for k, v in table.items() if not k.startswith("_") and _fields(k) != _fields(v)]
    assert not bad


@pytest.mark.parametrize("code", LANGS)
def test_format_with_the_english_fields(code):
    with open(os.path.join(TRANS, code + ".json"), encoding="utf-8") as fh:
        table = json.load(fh)
    for key, value in table.items():
        if key.startswith("_"):
            continue
        names = {n: 1 for n, _s in _fields(key)}
        value.format(**names)            # raises if a field is unknown


def test_tr_falls_back_to_english(language):
    from freecad.assembly_companion import i18n
    language("fr")
    assert i18n.tr("Freeze parts") != "Freeze parts"
    assert i18n.tr("A text nobody translated") == "A text nobody translated"
    language("en")
    assert i18n.tr("Freeze parts") == "Freeze parts"
