# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Generate thumbnails (GUI): files saved without thumbnail get a 256 px
one in a COPY of the folder; the original files are not touched; open
documents are skipped; FreeCAD's thumbnail settings are restored."""

import os

import pytest

pytestmark = pytest.mark.gui


def test_thumbnails_on_a_copy(tmp_path):
    import FreeCAD as App
    from freecad.assembly_companion import api, thumbs
    g = App.ParamGet(thumbs.DOC_PARAMS)
    settings = (g.GetBool("SaveThumbnail", False), g.GetInt("ThumbnailSize", 128))
    lib = tmp_path / "lib"
    lib.mkdir()
    before = set(App.listDocuments())
    try:
        g.SetBool("SaveThumbnail", False)
        for name in ("a", "b"):
            d = App.newDocument("ac_th_" + name)
            d.addObject("Part::Box", "Box")
            d.recompute()
            d.saveAs(str(lib / (name + ".FCStd")))
            App.closeDocument(d.Name)
        g.SetBool("SaveThumbnail", settings[0])
        originals = {p: os.path.getmtime(p) for p in thumbs.fcstd_files(str(lib))}
        assert len(api.files_without_thumbnail(str(lib))) == 2
        r = api.generate_thumbnails(str(lib))
        assert r["folder"] == str(lib) + "_thumbnails" and len(r["done"]) == 2, r
        assert api.files_without_thumbnail(r["folder"]) == []
        assert all(thumbs.thumbnail_width(p) >= 256 for p in thumbs.fcstd_files(r["folder"]))
        assert {p: os.path.getmtime(p) for p in thumbs.fcstd_files(str(lib))} == originals
        assert (g.GetBool("SaveThumbnail", False), g.GetInt("ThumbnailSize", 128)) == settings
    finally:
        g.SetBool("SaveThumbnail", settings[0])
        g.SetInt("ThumbnailSize", settings[1])
        for n in set(App.listDocuments()) - before:
            App.closeDocument(n)
    assert set(App.listDocuments()) == before
