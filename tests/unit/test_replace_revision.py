# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Next revision proposed by replace.py (AB_001a -> AB_001b...)."""

import os

import pytest

from freecad.assembly_companion import replace

pytestmark = pytest.mark.unit


def _touch(folder, *names):
    for n in names:
        (folder / n).write_text("")


def test_next_revision_picks_the_latest(tmp_path):
    _touch(tmp_path, "AB_001a_Plate.FCStd", "AB_001b_Plate.FCStd", "AB_001c_Plate.FCStd",
           "AB_002a_Other.FCStd")
    got = replace.next_revision(str(tmp_path / "AB_001a_Plate.FCStd"))
    assert os.path.basename(got) == "AB_001c_Plate.FCStd"


def test_next_revision_after_z(tmp_path):
    _touch(tmp_path, "AB_001z_P.FCStd", "AB_001aa_P.FCStd")
    got = replace.next_revision(str(tmp_path / "AB_001z_P.FCStd"))
    assert os.path.basename(got) == "AB_001aa_P.FCStd"


def test_no_later_revision(tmp_path):
    _touch(tmp_path, "AB_001c_Plate.FCStd", "AB_001a_Plate.FCStd")
    assert replace.next_revision(str(tmp_path / "AB_001c_Plate.FCStd")) is None


def test_file_without_revision_scheme(tmp_path):
    _touch(tmp_path, "plate.FCStd", "plate2.FCStd")
    assert replace.next_revision(str(tmp_path / "plate.FCStd")) is None
    assert replace.next_revision("") is None


def test_revision_without_letter(tmp_path):
    _touch(tmp_path, "AB_001_Plate.FCStd", "AB_001a_Plate.FCStd")
    got = replace.next_revision(str(tmp_path / "AB_001_Plate.FCStd"))
    assert os.path.basename(got) == "AB_001a_Plate.FCStd"
