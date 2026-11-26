# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Readers of the library previews (no Qt): STL binary and ASCII, 3MF
mesh and thumbnail, PNG size of a FreeCAD thumbnail, sampling."""

import struct
import zipfile

import pytest

from freecad.assembly_companion import previews

pytestmark = pytest.mark.unit

TRI = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def binary_stl(path, n):
    with open(path, "wb") as fh:
        fh.write(b"\0" * 80 + struct.pack("<I", n))
        for i in range(n):
            fh.write(struct.pack("<12fH", 0, 0, 1, i, 0, 0, i + 1, 0, 0, i, 1, 0, 0))


def test_kind():
    assert previews.kind("a/B.FCStd") == "freecad" and previews.kind("x.STP") == "step"
    assert previews.kind("m.3mf") == "mesh" and previews.kind("d.PDF") == "pdf"
    assert previews.kind("notes.txt") == ""


def test_binary_stl_sampled(tmp_path):
    p = str(tmp_path / "m.stl")
    binary_stl(p, 10)
    tris = previews.read_stl(p)
    assert len(tris) == 10 and tris[3][0] == (3.0, 0.0, 0.0)
    assert len(previews.read_stl(p, limit=4)) == 4


def test_ascii_stl(tmp_path):
    p = tmp_path / "a.stl"
    p.write_text("solid x\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\n"
                 "vertex 0 1 0\nendloop\nendfacet\nendsolid x\n")
    assert previews.read_stl(str(p)) == [TRI]


def test_3mf_mesh_and_thumbnail(tmp_path):
    p = str(tmp_path / "m.3mf")
    model = ('<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             '<resources><object id="1"><mesh><vertices><vertex x="0" y="0" z="0"/>'
             '<vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/></vertices>'
             '<triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object>'
             '</resources></model>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("3D/3dmodel.model", model)
    assert previews.read_3mf(p) == [TRI] and previews.threemf_thumbnail(p) is None
    with zipfile.ZipFile(p, "a") as z:
        z.writestr("Metadata/thumbnail.png", b"\x89PNG data")
    assert previews.threemf_thumbnail(p) == b"\x89PNG data"


def test_png_size():
    head = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", 256, 128)
    assert previews.png_size(head) == (256, 128)
    assert previews.png_size(b"nope") == (0, 0)


def test_broken_files_give_nothing(tmp_path):
    p = tmp_path / "bad.3mf"
    p.write_bytes(b"not a zip")
    assert previews.read_3mf(str(p)) == [] and previews.threemf_thumbnail(str(p)) is None
