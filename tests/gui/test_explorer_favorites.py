# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Explorer favourites and tags (GUI): a favourite folder is pinned on top,
a tag shows on the card, "Favorites only" filters, a favourite that no
longer exists is reported without breaking anything. The user's favourites,
tags and library folder are restored afterwards."""

import os
import shutil
import time

import pytest

pytestmark = pytest.mark.gui

KEYS = ("LocalMasterDir", "ExplorerFavorites", "ExplorerTags")


@pytest.fixture
def explorer_lib(tmp_path, monkeypatch):
    import FreeCAD as App
    from freecad.assembly_companion import explorer, library, prefs
    root = tmp_path / "lib"
    for f in ("A", "B", "C"):
        (root / f).mkdir(parents=True)
        (root / f / (f + "1.FCStd")).touch()
    cache = tmp_path / "cache"
    (cache / "thumbs").mkdir(parents=True)
    monkeypatch.setattr(library, "cache_dir", lambda: str(cache))
    monkeypatch.setattr(explorer, "cache_dir", lambda: str(cache))
    grp = App.ParamGet(prefs.PARAM_PATH)
    unset = "<ac-test-unset>"
    saved = {k: grp.GetString(k, unset) for k in KEYS}
    prefs.put("LocalMasterDir", "")
    library.clear_favorites_and_tags()
    w = explorer.ExplorerWidget(mode="open")
    w.path_edit.setText(str(root))
    w.refresh()
    _wait(w)
    yield w, str(root)
    w.close()
    w.deleteLater()
    for k, v in saved.items():
        if v == unset:
            grp.RemString(k)
        else:
            grp.SetString(k, v)


def _wait(w, timeout=10.0):
    from PySide import QtWidgets
    end = time.time() + timeout
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        if not w.scan_jobs and w.current_scan is not None:
            return
        time.sleep(0.02)
    raise AssertionError("scan did not finish")


def test_favorite_pinned_on_top(explorer_lib):
    w, root = explorer_lib
    assert [b[2] for b in w.blocks] == ["", "a", "b", "c"]
    w.toggle_favorite(os.path.join(root, "C"))
    assert [b[2] for b in w.blocks][0] == "c"
    w.toggle_favorite(os.path.join(root, "C"))
    assert [b[2] for b in w.blocks] == ["", "a", "b", "c"]


def test_tag_on_card(explorer_lib):
    w, root = explorer_lib
    path = os.path.join(root, "B", "B1.FCStd")
    assert w.set_tag(path, "urgent") == "#urgent"
    card = w.cards[path]
    assert card.badge.text() == "#urgent" and not card.badge.isHidden()
    w.set_tag(path, "")
    assert card.badge.isHidden()


def test_favorites_only_filter(explorer_lib):
    w, root = explorer_lib
    w.toggle_favorite(os.path.join(root, "A"))
    w.favs_only.setChecked(True)
    visible = [b[2] for b in w.blocks if not b[0].isHidden()]
    assert visible == ["a"]
    w.favs_only.setChecked(False)


def test_missing_favorite_is_reported(explorer_lib):
    w, root = explorer_lib
    b = os.path.join(root, "B")
    w.toggle_favorite(b)
    shutil.rmtree(b)
    w.refresh()
    _wait(w)
    assert "b" not in [x[2] for x in w.blocks]
    assert "★" in w.status.text()
    w._fill_favorites_menu()
    texts = [a.text() for a in w.favs_menu.actions()]
    assert any(b in t for t in texts)
    w._remove_missing_favorites()
    from freecad.assembly_companion import library
    assert library.missing_favorites(root) == []
