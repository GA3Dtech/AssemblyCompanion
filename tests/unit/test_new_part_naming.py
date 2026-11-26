# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""File naming of new_part.py: PREFIX_001a_Description."""

import pytest

from freecad.assembly_companion import new_part

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("args, expected", [
    (("AB", 1, 3, "a", "Bracket"), "AB_001a_Bracket.FCStd"),
    (("AB", 12, 3, "", ""), "AB_012.FCStd"),
    (("", 7, 3, "b", "Plate"), "007b_Plate.FCStd"),
    (("XY", 5, 4, "c", "Two words"), "XY_0005c_Two words.FCStd"),
    (("A/B", 1, 3, "a", 'Bad:*?"<>|name'), "AB_001a_Badname.FCStd"),
    (("AB", 1234, 3, "a", "Big"), "AB_1234a_Big.FCStd"),
])
def test_file_name(args, expected):
    assert new_part.file_name(*args) == expected


def test_next_number(tmp_path):
    for name in ("AB_001a_X.FCStd", "AB_004c_Y.FCStd", "ab_007a_Z.FCStd",
                 "AC_009a_Z.FCStd", "notes.txt", "AB_xyz.FCStd"):
        (tmp_path / name).write_text("")
    assert new_part.next_number(str(tmp_path), "AB") == 8      # case-insensitive
    assert new_part.next_number(str(tmp_path), "AC") == 10
    assert new_part.next_number(str(tmp_path), "ZZ") == 1
    assert new_part.next_number(str(tmp_path / "missing"), "AB") == 1


def test_next_number_without_prefix(tmp_path):
    (tmp_path / "003b_Plate.FCStd").write_text("")
    assert new_part.next_number(str(tmp_path), "") == 4


def test_folder_prefix(tmp_path):
    from freecad.assembly_companion import new_part
    work = tmp_path / "GI_MiniEtau"
    work.mkdir()
    assert new_part.folder_prefix(str(work)) == "GI"            # from the folder name
    for n in ("AB_001a_x.FCStd", "AB_002a_y.FCStd", "CD_001a_z.FCStd", "AB_003a.step"):
        (work / n).touch()
    assert new_part.folder_prefix(str(work)) == "AB"            # files win, most used
    for name in ("parts", "new_parts"):
        plain = tmp_path / name
        plain.mkdir()
        assert new_part.folder_prefix(str(plain)) == ""
    assert new_part.folder_prefix(str(tmp_path / "missing")) == ""
