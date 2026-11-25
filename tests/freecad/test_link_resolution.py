# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Behaviour of FreeCAD itself that the workbench relies on: the Links of a
project folder copied elsewhere (the original still there) resolve to the
files of the COPY. FreeCAD 1.1 and 26.3 do; the weekly build (future 27.1)
resolved them to the original files, which broke archive, outdated parts,
relink after moving... On failure the message tells which FreeCAD and how
the link path is stored, to follow the change upstream."""

import os
import re
import shutil
import zipfile

import pytest

from conftest import close_all

pytestmark = pytest.mark.freecad

App = pytest.importorskip("FreeCAD")


def _stored_paths(fcstd):
    with zipfile.ZipFile(fcstd) as z:
        xml = z.read("Document.xml").decode("utf-8", "replace")
    return sorted(set(re.findall(r'<XLink file="([^"]*)"', xml)))


def test_links_of_a_copied_project_resolve_to_the_copy(tmp_path):
    import Part
    original = tmp_path / "original"
    original.mkdir()
    src = App.newDocument("lr_part")
    box = src.addObject("Part::Feature", "Box")
    box.Shape = Part.makeBox(1, 1, 1)
    src.saveAs(str(original / "part.FCStd"))
    asm = App.newDocument("lr_asm")
    asm.saveAs(str(original / "asm.FCStd"))
    lk = asm.addObject("App::Link", "L")
    lk.setLink(box)
    asm.recompute()
    asm.save()
    close_all()
    copy = tmp_path / "copy"
    shutil.copytree(str(original), str(copy))
    doc = App.openDocument(str(copy / "asm.FCStd"))
    target = doc.getObject("L").LinkedObject
    resolved = target.Document.FileName if target is not None else None
    info = "FreeCAD %s; stored link paths %s; resolved to %s" % (
        ".".join(App.Version()[:4]), _stored_paths(str(copy / "asm.FCStd")), resolved)
    assert resolved and os.path.samefile(resolved, str(copy / "part.FCStd")), info
