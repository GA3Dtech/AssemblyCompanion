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
def cache_dir():
    base = None
    for fn in ("getUserCachePath", "getUserAppDataDir"):
        try:
            base = getattr(App, fn)()
            if base:
                break
        except Exception:
            pass
    d = os.path.join(base or os.path.expanduser("~"), "assembly_explorer_cache")
    os.makedirs(os.path.join(d, "thumbs"), exist_ok=True)
    return d


def cache_key(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


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
