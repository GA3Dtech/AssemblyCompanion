# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parts library scan: scan_folder / merge_scan on a temporary tree (empty
.FCStd files: the scan never opens them)."""

import os
import threading
import time

import pytest

from freecad.assembly_companion import library

pytestmark = pytest.mark.unit


def touch(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "lib"
    for rel in ("A/a1.FCStd", "A/a2.fcstd", "A/notes.txt", "A/Sub/s1.FCStd",
                "B/b1.FCStd", ".hidden/h.FCStd", "C/D/d1.FCStd", "top.FCStd"):
        touch(str(root / rel))
    return str(root)


def names(scan, folder):
    return [os.path.basename(f[0]) for f in scan.get(folder, [])]


def test_scan_folder_recursive(tree):
    scan = library.scan_folder(tree, recursive=True)
    j = lambda *p: os.path.join(tree, *p)
    assert set(scan) == {tree, j("A"), j("A", "Sub"), j("B"), j("C", "D")}
    assert names(scan, j("A")) == ["a1.FCStd", "a2.fcstd"]     # sorted, case-insensitive ext
    assert names(scan, tree) == ["top.FCStd"]
    assert all(len(f) == 3 for files in scan.values() for f in files)


def test_scan_folder_not_recursive(tree):
    a = os.path.join(tree, "A")
    assert set(library.scan_folder(a, recursive=False)) == {a}
    assert library.scan_folder(os.path.join(tree, "C"), recursive=False) == {}


def test_hidden_folders_skipped(tree):
    scan = library.scan_master(tree)
    assert not any(".hidden" in d for d in scan)


def test_missing_folder_is_empty(tmp_path):
    assert library.scan_folder(str(tmp_path / "nope")) == {}


def test_trailing_separator_gives_same_keys(tree):
    assert library.scan_folder(tree + os.sep) == library.scan_folder(tree)


# --- merge_scan --------------------------------------------------------
def refresh(scan, folder, recursive):
    return library.merge_scan(scan, folder, library.scan_folder(folder, recursive), recursive)


def test_merge_unchanged(tree):
    scan = library.scan_master(tree)
    new, changed = refresh(scan, os.path.join(tree, "A"), False)
    assert changed == [] and new == scan


def test_merge_file_added(tree):
    scan = library.scan_master(tree)
    a = os.path.join(tree, "A")
    touch(os.path.join(a, "a3.FCStd"))
    new, changed = refresh(scan, a, False)
    assert changed == [a]
    assert names(new, a) == ["a1.FCStd", "a2.fcstd", "a3.FCStd"]
    assert new[os.path.join(tree, "B")] == scan[os.path.join(tree, "B")]


def test_merge_file_removed_and_modified(tree):
    scan = library.scan_master(tree)
    a = os.path.join(tree, "A")
    os.remove(os.path.join(a, "a1.FCStd"))
    touch(os.path.join(a, "a2.fcstd"), b"bigger now")
    new, changed = refresh(scan, a, False)
    assert changed == [a]
    assert names(new, a) == ["a2.fcstd"]
    assert new[a][0][2] == len(b"bigger now")


def test_merge_not_recursive_keeps_subfolders(tree):
    scan = library.scan_master(tree)
    a, sub = os.path.join(tree, "A"), os.path.join(tree, "A", "Sub")
    touch(os.path.join(sub, "s2.FCStd"))          # not seen by a flat refresh of A
    new, changed = refresh(scan, a, False)
    assert changed == [] and names(new, sub) == ["s1.FCStd"]
    new, changed = refresh(scan, a, True)
    assert changed == [sub] and names(new, sub) == ["s1.FCStd", "s2.FCStd"]


def test_merge_new_folder(tree):
    scan = library.scan_master(tree)
    e = os.path.join(tree, "B", "E")
    touch(os.path.join(e, "e1.FCStd"))
    new, changed = refresh(scan, os.path.join(tree, "B"), True)
    assert changed == [e] and names(new, e) == ["e1.FCStd"]


def test_merge_folder_became_empty(tree):
    scan = library.scan_master(tree)
    b = os.path.join(tree, "B")
    os.remove(os.path.join(b, "b1.FCStd"))
    new, changed = refresh(scan, b, False)
    assert changed == [b] and b not in new


def test_merge_whole_subtree_removed(tree):
    import shutil
    scan = library.scan_master(tree)
    a = os.path.join(tree, "A")
    shutil.rmtree(a)
    new, changed = refresh(scan, a, True)
    assert changed == [a, os.path.join(a, "Sub")]
    assert not any(library.is_inside(d, a) for d in new)
    assert len(new) == len(scan) - 2


def test_merge_does_not_touch_sibling_with_same_prefix(tree):
    """A refresh of A must not remove 'AB' (prefix match is not containment)."""
    touch(os.path.join(tree, "AB", "x.FCStd"))
    scan = library.scan_master(tree)
    a = os.path.join(tree, "A")
    os.remove(os.path.join(a, "a1.FCStd"))
    os.remove(os.path.join(a, "a2.fcstd"))
    os.remove(os.path.join(a, "Sub", "s1.FCStd"))
    new, changed = refresh(scan, a, True)
    assert os.path.join(tree, "AB") in new
    assert changed == [a, os.path.join(a, "Sub")]


def test_merge_full_rescan_reports_only_differences(tree):
    scan = library.scan_master(tree)
    touch(os.path.join(tree, "C", "D", "d2.FCStd"))
    new, changed = refresh(scan, tree, True)
    assert changed == [os.path.join(tree, "C", "D")]
    assert new == library.scan_master(tree)


def test_merge_accepts_cached_lists(tree):
    """The JSON cache gives lists instead of tuples: no false change."""
    scan = library.scan_master(tree)
    cached = {d: [list(f) for f in files] for d, files in scan.items()}
    _new, changed = refresh(cached, tree, True)
    assert changed == []


def test_view_folders_order_and_parents(tree):
    scan = library.scan_master(tree)
    folders = library.view_folders(tree, scan)
    rel = [os.path.relpath(d, tree) for d in folders]
    assert rel == [".", "A", os.path.join("A", "Sub"), "B", "C", os.path.join("C", "D")]


# --- performance: a targeted refresh lists only its folder ---------------
@pytest.fixture
def big_tree(tmp_path):
    """3600 files in 200 folders (10 groups x 20 folders x 18 files)."""
    root = tmp_path / "big"
    for g in range(10):
        for f in range(20):
            d = root / ("G%02d" % g) / ("F%02d" % f)
            d.mkdir(parents=True)
            for i in range(18):
                (d / ("P%02d_%03d.FCStd" % (f, i))).touch()
    return str(root)


def test_targeted_refresh_lists_one_folder(big_tree, monkeypatch):
    scan = library.scan_master(big_tree)
    assert sum(len(v) for v in scan.values()) == 3600 and len(scan) == 200
    calls = []
    real = os.scandir

    def spy(path="."):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(library.os, "scandir", spy)
    folder = os.path.join(big_tree, "G03", "F07")
    open(os.path.join(folder, "new.FCStd"), "wb").close()
    new, changed = refresh(scan, folder, False)
    assert calls == [folder]
    assert changed == [folder] and len(new[folder]) == 19

    calls.clear()
    refresh(scan, os.path.join(big_tree, "G03"), True)
    assert len(calls) == 21          # G03 + its 20 folders

    calls.clear()
    library.scan_master(big_tree)
    assert len(calls) == 211         # root + 10 groups + 200 folders


# --- concurrency: results applied in submission order ------------------
def test_slow_full_scan_does_not_override_targeted(tree):
    """The explorer runs every scan (full or targeted) on ONE worker thread
    and applies results in submission order: a slow full scan started
    before a targeted refresh can never land after it."""
    import concurrent.futures
    a = os.path.join(tree, "A")
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    started = threading.Event()

    def slow_full():
        snapshot = library.scan_master(tree)      # read BEFORE the new file exists
        started.set()
        time.sleep(0.3)
        return snapshot

    jobs = [(tree, True, pool.submit(slow_full))]
    started.wait(5)
    touch(os.path.join(a, "late.FCStd"))
    jobs.append((a, False, pool.submit(library.scan_folder, a, False)))
    scan = {}
    for folder, rec, fut in jobs:                 # the explorer's _drain order
        scan, _changed = library.merge_scan(scan, folder, fut.result(), rec)
    pool.shutdown()
    assert "late.FCStd" in names(scan, a)


# --- disk cache: size, clearing one master or everything -----------------
def test_clear_cache_of_one_master(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    (cache / "thumbs").mkdir(parents=True)
    monkeypatch.setattr(library, "cache_dir", lambda: str(cache))
    libs = {}
    for name in ("old", "new"):
        root = tmp_path / name
        touch(str(root / "A" / (name + ".FCStd")))
        scan = library.scan_master(str(root))
        library.save_scan_cache(str(root), scan)
        for files in scan.values():
            for p, m, s in files:
                (cache / "thumbs" / (library.thumb_key(p, m, s) + ".png")).write_bytes(b"x" * 100)
        libs[name] = str(root)
    assert library.master_cache_bytes(libs["old"]) > 100
    freed = library.clear_cache(libs["old"])
    assert freed > 100
    assert library.load_scan_cache(libs["old"]) is None
    assert library.load_scan_cache(libs["new"]) is not None
    assert len(list((cache / "thumbs").iterdir())) == 1           # the new one stays
    assert library.master_cache_bytes(libs["old"]) == 0
    info = library.cache_info()
    assert info["files"] == 2 and info["bytes"] > 100
    library.clear_cache()
    assert library.cache_info()["files"] == 0


def test_human_size():
    assert library.human_size(512) == "512 B"
    assert library.human_size(12 * 1024 * 1024) == "12.0 MB"


# --- configurable cache folder ----------------------------------------
def test_cache_folder_from_preference_and_private(tmp_path):
    import stat
    from freecad.assembly_companion import prefs
    old = prefs.get("ExplorerCacheDir")
    try:
        prefs.put("ExplorerCacheDir", str(tmp_path / "mycache"))
        d = library.cache_dir()
        assert d == str(tmp_path / "mycache")
        assert os.path.isdir(os.path.join(d, "thumbs"))
        if os.name == "posix":
            assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
        prefs.put("ExplorerCacheDir", "")
        assert library.cache_dir() == library.default_cache_dir()
    finally:
        prefs.put("ExplorerCacheDir", old)


def test_move_cache(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    (old / "thumbs").mkdir(parents=True)
    (old / "scan_x.json").write_text("{}")
    (old / "thumbs" / "a.png").write_bytes(b"png")
    (new / "thumbs").mkdir(parents=True)
    (new / "thumbs" / "b.png").write_bytes(b"kept")
    assert library.move_cache(str(old), str(new)) == 2
    assert not old.exists()
    assert sorted(p.name for p in (new / "thumbs").iterdir()) == ["a.png", "b.png"]
    assert (new / "scan_x.json").exists()
    assert library.move_cache(str(new), str(new)) == 0


# --- favourites and tags -----------------------------------------------
@pytest.fixture
def clean_prefs():
    from freecad.assembly_companion import prefs
    saved = prefs.get("ExplorerFavorites"), prefs.get("ExplorerTags")
    library.clear_favorites_and_tags()
    yield
    prefs.put("ExplorerFavorites", saved[0])
    prefs.put("ExplorerTags", saved[1])


def test_favorites_pinned_first(tree, clean_prefs):
    scan = library.scan_master(tree)
    folders = library.view_folders(tree, scan)
    c_d = os.path.join(tree, "C", "D")
    b = os.path.join(tree, "B")
    library.set_favorite(c_d, True)
    library.set_favorite(b, True)
    assert library.is_favorite(c_d + os.sep) and library.favorites() == [c_d, b]
    ordered = library.order_with_favorites(folders)
    assert ordered[:2] == [c_d, b] and sorted(ordered) == sorted(folders)
    library.set_favorite(c_d, False)
    assert library.order_with_favorites(folders)[0] == b


def test_missing_favorite_does_not_break(tree, clean_prefs):
    import shutil
    b = os.path.join(tree, "B")
    library.set_favorite(b, True)
    shutil.rmtree(b)
    scan = library.scan_master(tree)
    folders = library.view_folders(tree, scan)
    assert b not in library.order_with_favorites(folders)
    assert library.missing_favorites(tree) == [b]
    assert library.missing_favorites(os.path.join(tree, "A")) == []


def test_tags(tree, clean_prefs):
    f = os.path.join(tree, "A", "a1.FCStd")
    assert library.set_tag(f, "  urgent ") == "#urgent"
    assert library.tag_of(f) == "#urgent"
    assert library.set_tag(f, "😀") == "😀"
    assert library.set_tag(f, "#averyveryverylongtag") == "#averyveryve"
    assert library.set_tag(f, "") == "" and library.tag_of(f) == ""


def test_corrupted_preferences_are_ignored(clean_prefs):
    from freecad.assembly_companion import prefs
    prefs.put("ExplorerFavorites", "{not json")
    prefs.put("ExplorerTags", "[1, 2]")
    assert library.favorites() == [] and library.tags() == {}
