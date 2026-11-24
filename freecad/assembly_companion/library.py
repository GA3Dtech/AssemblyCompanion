# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - parts library scan (no GUI)
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""
library.py (Assembly Companion) - scan of the parts library folder, shared by
the explorer, the visual insertion dock and the API. Pure Python (no Qt), so
it runs headless and in unit tests.

A scan is a dict {folder: [(path, mtime, size), ...]} holding only the
folders that contain .FCStd files directly, files sorted by name.

Targeted refresh: a library of thousands of files on a network share is too
slow to walk again after each new part. scan_folder() reads one folder (or
one subtree), merge_scan() puts the result into the full scan and returns the
folders that really changed, so the views rebuild only those.
"""

import os
import json
import hashlib

try:
    import FreeCAD as App
except ImportError:                       # plain Python (tools, tests)
    App = None


# ----------------------------------------------------------------------
#  Paths
# ----------------------------------------------------------------------
def norm(path):
    """Comparable form of a path (case-insensitive on Windows)."""
    return os.path.normcase(os.path.normpath(path))


def is_inside(path, folder, recursive=True):
    """True if `path` is `folder` or, when recursive, one of its subfolders."""
    p, f = norm(path), norm(folder)
    if p == f:
        return True
    return recursive and p.startswith(f.rstrip(os.sep) + os.sep)


# ----------------------------------------------------------------------
#  Folder scan (runs in a worker thread)
# ----------------------------------------------------------------------
def scan_folder(path, recursive=True):
    """Return {folder: [(path, mtime, size), ...]} for `path` (and its
    subfolders when recursive). os.scandir gives size / date without an extra
    request per file on Windows (they come with the listing). Hidden folders
    (name starting with a dot) are skipped."""
    result = {}

    def walk(d):
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            return
        files, subdirs = [], []
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if not e.name.startswith('.'):
                        subdirs.append(e.path)
                elif e.name.lower().endswith(".fcstd"):
                    st = e.stat()
                    files.append((e.path, st.st_mtime, st.st_size))
            except OSError:
                pass
        if files:
            files.sort(key=lambda f: os.path.basename(f[0]).lower())
            result[d] = files
        if recursive:
            for s in sorted(subdirs, key=str.lower):
                walk(s)

    walk(os.path.normpath(path))
    return result


def scan_master(master):
    """Full scan of the library."""
    return scan_folder(master, recursive=True)


def _files(entries):
    return [tuple(f) for f in entries or []]


def merge_scan(scan, folder, partial, recursive):
    """Put the result of scan_folder(folder, recursive) into `scan`.

    Returns (new_scan, changed_folders): the entries of `folder` (and of its
    subtree when recursive) are replaced by `partial`, folders that became
    empty are dropped, new ones are added. changed_folders lists the folders
    whose file list really differs (added, removed or modified), sorted.
    `scan` itself is not modified."""
    old_part, new = {}, {}
    for d, files in scan.items():
        if is_inside(d, folder, recursive):
            old_part[norm(d)] = (d, _files(files))
        else:
            new[d] = files
    new_part = {}
    for d, files in partial.items():
        if files and is_inside(d, folder, recursive):
            new[d] = _files(files)
            new_part[norm(d)] = (d, _files(files))
    changed = []
    for key in set(old_part) | set(new_part):
        old, cur = old_part.get(key), new_part.get(key)
        if old is None or cur is None or old[1] != cur[1]:
            changed.append((cur or old)[0])
    return new, sorted(changed, key=norm)


def view_folders(master, scan):
    """Folders shown by the explorer, in display order: those holding files
    plus all their parents up to `master`, sorted by path."""
    relevant = {os.path.normpath(master)}
    nm = norm(master)
    for d in scan:
        cur = d
        while True:
            relevant.add(os.path.normpath(cur))
            if norm(cur) == nm:
                break
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return sorted(relevant, key=lambda d: folder_sort_key(master, d))


def folder_sort_key(master, folder):
    """Sort key of a folder in the explorer; its length is the tree depth."""
    rel = os.path.relpath(folder, master)
    return () if rel == "." else tuple(p.lower() for p in rel.split(os.sep))


# ----------------------------------------------------------------------
#  Disk cache (scan results and thumbnails)
# ----------------------------------------------------------------------
def default_cache_dir():
    """FreeCAD's user cache folder (some systems empty it often: the
    preference ExplorerCacheDir can point elsewhere)."""
    base = None
    for fn in ("getUserCachePath", "getUserAppDataDir"):
        try:
            base = getattr(App, fn)()
            if base:
                break
        except Exception:
            pass
    return os.path.join(base or os.path.expanduser("~"), "assembly_explorer_cache")


def _private(path):
    """Folder readable and writable by the current user only (POSIX; on
    Windows the user profile is private already)."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    if os.name == "posix":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


def cache_dir():
    """Explorer cache folder: the ExplorerCacheDir preference, else the
    default one. Created private to the current user."""
    d = ""
    try:
        from . import prefs
        d = prefs.get("ExplorerCacheDir")
    except Exception:
        pass
    d = d or default_cache_dir()
    _private(d)
    _private(os.path.join(d, "thumbs"))
    return d


def move_cache(old, new):
    """Move the content of the cache folder `old` into `new` (files already
    in `new` are kept). Returns the number of files moved."""
    import shutil
    if not old or not os.path.isdir(old) or norm(old) == norm(new):
        return 0
    _private(new)
    n = 0
    for dirpath, _dirs, files in os.walk(old):
        rel = os.path.relpath(dirpath, old)
        dst_dir = os.path.join(new, rel) if rel != "." else new
        _private(dst_dir)
        for f in files:
            dst = os.path.join(dst_dir, f)
            if not os.path.exists(dst):
                try:
                    shutil.move(os.path.join(dirpath, f), dst)
                    n += 1
                except OSError:
                    pass
    shutil.rmtree(old, ignore_errors=True)
    return n


def cache_key(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def thumb_key(path, mtime, size):
    """Name (without extension) of the cached thumbnail of a file version."""
    return cache_key(os.path.normcase(path), mtime, size)


def _scan_cache_file(master):
    return os.path.join(cache_dir(), "scan_%s.json" % cache_key(os.path.normcase(master)))


def load_scan_cache(master):
    try:
        with open(_scan_cache_file(master), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {d: _files(files) for d, files in data.items()}
    except Exception:
        return None


def save_scan_cache(master, scan):
    try:
        with open(_scan_cache_file(master), "w", encoding="utf-8") as fh:
            json.dump(scan, fh)
    except Exception:
        pass


def _tree_size(path):
    total, count = 0, 0
    for dirpath, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
                count += 1
            except OSError:
                pass
    return total, count


def cache_info():
    """{"path", "bytes", "files"} of the explorer disk cache."""
    path = cache_dir()
    size, count = _tree_size(path)
    return {"path": path, "bytes": size, "files": count}


def master_cache_bytes(master):
    """Disk space of the cached scan and thumbnails of one master folder."""
    scan = load_scan_cache(master)
    if scan is None:
        return 0
    thumbs = os.path.join(cache_dir(), "thumbs")
    total = os.path.getsize(_scan_cache_file(master))
    for files in scan.values():
        for path, mtime, size in files:
            for ext in (".png", ".none"):
                f = os.path.join(thumbs, thumb_key(path, mtime, size) + ext)
                if os.path.exists(f):
                    total += os.path.getsize(f)
    return total


def clear_cache(master=None):
    """Delete the cache of one master folder (its scan and the thumbnails of
    the files it lists), or the whole cache when master is None. Returns the
    bytes freed. Only rebuilds cost: the next scan reads the folder and
    unzips the thumbnails again."""
    root = cache_dir()
    if master is None:
        size, _count = _tree_size(root)
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                try:
                    os.remove(os.path.join(dirpath, f))
                except OSError:
                    pass
        return size
    freed = master_cache_bytes(master)
    scan = load_scan_cache(master) or {}
    thumbs = os.path.join(root, "thumbs")
    for files in scan.values():
        for path, mtime, size in files:
            for ext in (".png", ".none"):
                try:
                    os.remove(os.path.join(thumbs, thumb_key(path, mtime, size) + ext))
                except OSError:
                    pass
    try:
        os.remove(_scan_cache_file(master))
    except OSError:
        pass
    return freed


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024.0
