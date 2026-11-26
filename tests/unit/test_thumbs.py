# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Thumbnails tool, file side: which files lack a 256 px thumbnail, and the
copy of a folder keeps the sub-folders (links between files keep working)."""

import os
import struct
import zipfile

import pytest

from freecad.assembly_companion import thumbs

pytestmark = pytest.mark.unit


def fcstd(path, width=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Document.xml", "<Document/>")
        if width:
            png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", width, width)
            z.writestr("thumbnails/Thumbnail.png", png)


def test_missing_and_copy(tmp_path):
    lib = tmp_path / "lib"
    fcstd(str(lib / "a.FCStd"), 256)
    fcstd(str(lib / "b.FCStd"), 128)
    fcstd(str(lib / "sub" / "c.FCStd"))
    (lib / "notes.txt").write_text("x")
    names = lambda paths: sorted(os.path.relpath(p, str(lib)) for p in paths)
    assert names(thumbs.missing(str(lib))) == ["b.FCStd", os.path.join("sub", "c.FCStd")]
    assert names(thumbs.missing(str(lib), recursive=False)) == ["b.FCStd"]
    dest = thumbs.copy_folder(str(lib))
    assert dest == str(lib) + "_thumbnails"
    assert sorted(os.path.relpath(p, dest) for p in thumbs.fcstd_files(dest)) == \
        ["a.FCStd", "b.FCStd", os.path.join("sub", "c.FCStd")]
    assert thumbs.copy_folder(str(lib)) == str(lib) + "_thumbnails2"
    assert thumbs.thumbnail_width(str(lib / "a.FCStd")) == 256
