# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""CSV written by bom.write_csv: encoding, separator, special characters."""

import csv

import pytest

from freecad.assembly_companion import bom

pytestmark = pytest.mark.unit

ROWS = {
    ("Vis M3x20; tête", "visserie.FCStd", bom.FROZEN): 4,
    ("Plaque «a»", "AB_001a_Plate.FCStd", bom.LINKED): 1,
    ("bolt", "bolt.FCStd", bom.LIGHT): 2,
    ("Écrou", "écrou.FCStd", bom.LOCAL): 3,
}


def _read(path, sep):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh, delimiter=sep))


def test_english_uses_comma(tmp_path, language):
    language("en")
    p = tmp_path / "bom.csv"
    bom.write_csv(str(p), ROWS)
    rows = _read(p, ",")
    assert rows[0] == ["Quantity", "Part", "Source file", "State"]
    assert len(rows) == 5
    names = [r[1] for r in rows[1:]]
    assert names == sorted(names, key=str.lower)                 # sorted by name
    assert ["4", "Vis M3x20; tête", "visserie.FCStd", "frozen"] in rows


def test_french_uses_semicolon_and_keeps_quotes(tmp_path, language):
    language("fr")
    p = tmp_path / "bom.csv"
    bom.write_csv(str(p), ROWS)
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                       # BOM for spreadsheets
    rows = _read(p, ";")
    assert rows[0][0] == "Quantité"
    # the ';' inside a name is quoted, not a column break
    assert any(r[1] == "Vis M3x20; tête" and len(r) == 4 for r in rows)
    assert any(r[1] == "Écrou" for r in rows)
