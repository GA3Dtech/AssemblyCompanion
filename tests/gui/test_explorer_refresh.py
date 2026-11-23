# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Explorer targeted refresh (GUI): only the refreshed folder gets new cards,
scroll and filter stay, saves from FreeCAD refresh one folder, a slow full
scan does not undo a newer targeted refresh. Works on a temporary library;
the user's library folder setting is restored afterwards."""

import os
import time

import pytest

pytestmark = pytest.mark.gui

FOLDERS = ["F%d" % i for i in range(8)]
FILES = 4


def touch(path):
    open(path, "wb").close()


@pytest.fixture
def lib(tmp_path, monkeypatch):
    from freecad.assembly_companion import explorer, library, prefs
    root = tmp_path / "lib"
    for f in FOLDERS:
        (root / f).mkdir(parents=True)
        for i in range(FILES):
            touch(str(root / f / ("%s_%02d.FCStd" % (f, i))))
    cache = tmp_path / "cache"
    (cache / "thumbs").mkdir(parents=True)
    monkeypatch.setattr(library, "cache_dir", lambda: str(cache))
    monkeypatch.setattr(explorer, "cache_dir", lambda: str(cache))
    saved = {k: prefs.get(k) for k in ("LocalMasterDir", "ExplorerFullScan")}
    prefs.put("LocalMasterDir", "")            # no automatic scan at construction
    yield str(root)
    for k, v in saved.items():
        prefs.put(k, v)


def wait_idle(w, timeout=10.0):
    from PySide import QtWidgets
    end = time.time() + timeout
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        if not w.scan_jobs and w.current_scan is not None and not w.save_timer.isActive():
            for _ in range(5):
                QtWidgets.QApplication.processEvents()
            return
        time.sleep(0.02)
    raise AssertionError("explorer scan did not finish")


@pytest.fixture
def explorer_widget(lib):
    from freecad.assembly_companion import explorer
    widgets = []

    def make(mode="open"):
        w = explorer.ExplorerWidget(mode=mode)
        w.resize(700, 300)
        w.show()
        w.path_edit.setText(lib)
        w.refresh()
        wait_idle(w)
        widgets.append(w)
        return w
    yield make
    for w in widgets:
        w.close()
        w.deleteLater()


def total(w):
    return sum(len(v) for v in w.current_scan.values())


def test_targeted_refresh_rebuilds_one_folder(lib, explorer_widget):
    w = explorer_widget()
    assert total(w) == len(FOLDERS) * FILES
    created = w.cards_created
    keep = w.cards[os.path.join(lib, "F1", "F1_00.FCStd")]
    w.filter_edit.setText("F")
    w.apply_filter()
    bar = w.scroll.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    pos = bar.value()
    assert pos > 0

    touch(os.path.join(lib, "F5", "F5_99.FCStd"))
    w.refresh_folder(os.path.join(lib, "F5"))
    wait_idle(w)
    assert w.cards_created - created == FILES + 1          # only folder F5
    assert w.cards[os.path.join(lib, "F1", "F1_00.FCStd")] is keep
    assert os.path.join(lib, "F5", "F5_99.FCStd") in w.cards
    assert w.filter_edit.text() == "F"
    assert bar.value() == pos
    assert [b[2] for b in w.blocks] == [""] + [f.lower() for f in FOLDERS]


def test_refresh_all_only_rebuilds_differences(lib, explorer_widget):
    w = explorer_widget()
    created = w.cards_created
    os.remove(os.path.join(lib, "F2", "F2_00.FCStd"))
    w.refresh()
    wait_idle(w)
    assert w.cards_created - created == FILES - 1
    assert total(w) == len(FOLDERS) * FILES - 1


def test_removed_folder_block_disappears(lib, explorer_widget):
    import shutil
    w = explorer_widget()
    shutil.rmtree(os.path.join(lib, "F7"))
    w.refresh_folder(lib, recursive=True)
    wait_idle(w)
    assert "f7" not in [b[2] for b in w.blocks]
    assert w.tree_layout.count() == len(FOLDERS) + 1        # master + F0..F6 + stretch


@pytest.mark.parametrize("mode", ["open", "insert"])
def test_folder_headers_have_context_menu(lib, explorer_widget, mode):
    from PySide import QtCore, QtWidgets
    w = explorer_widget(mode)
    for block, _cards, _rel in w.blocks:
        heads = [c for c in block.findChildren(QtWidgets.QWidget)
                 if c.contextMenuPolicy() == QtCore.Qt.CustomContextMenu]
        assert heads, "folder header without context menu"


def test_save_from_freecad_refreshes_only_its_folder(lib, explorer_widget, monkeypatch,
                                                      tmp_path):
    import FreeCAD as App
    from freecad.assembly_companion import api, explorer
    w = explorer_widget()
    calls = []
    real = explorer.scan_folder

    def spy(folder, recursive=True):
        calls.append((folder, recursive))
        return real(folder, recursive)

    monkeypatch.setattr(explorer, "scan_folder", spy)
    src = App.newDocument("ac_explorer_src")
    box = src.addObject("Part::Box", "Box")
    src.recompute()
    src.saveAs(str(tmp_path / "src.FCStd"))
    calls.clear()
    path = os.path.join(lib, "F3", "F3_new.FCStd")
    res = None
    try:
        res = api.new_part_from_selection(src, [["Box", "Face6"]], path, insert=False)
        wait_idle(w)
        assert calls == [(os.path.join(lib, "F3"), False)]
        assert path in w.cards
    finally:
        App.closeDocument(src.Name)
        if res and res.get("document") in App.listDocuments():
            App.closeDocument(res["document"])
    del box


def test_slow_full_scan_does_not_undo_targeted_refresh(lib, explorer_widget, monkeypatch):
    from freecad.assembly_companion import explorer, library
    w = explorer_widget()

    def slow(folder, recursive=True):
        snap = library.scan_folder(folder, recursive)
        if recursive:
            time.sleep(0.5)                 # read before the new file, lands late
        return snap

    monkeypatch.setattr(explorer, "scan_folder", slow)
    w.refresh()                             # full scan starts
    time.sleep(0.1)
    late = os.path.join(lib, "F4", "F4_late.FCStd")
    touch(late)
    w.refresh_folder(os.path.join(lib, "F4"))
    wait_idle(w)
    assert late in w.cards
