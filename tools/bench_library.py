# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
tools/bench_library.py (Assembly Companion) - full library scan versus a
targeted folder refresh (explorer, visual insertion).

Plain Python, no FreeCAD needed:

    python3 tools/bench_library.py [--folders 200] [--files 18] [--latency-ms 0]

Builds a temporary tree (empty .FCStd files: the scan never opens them) and
times scan_master(), a one-folder refresh and a one-group refresh, each
merged with merge_scan(). --latency-ms adds a delay to every directory
listing (os.scandir), to mimic a network share where each listing is one
round trip (sizes and dates come with the listing on Windows).
"""

import argparse
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from freecad.assembly_companion import library  # noqa: E402


def build_tree(root, folders, files, groups=10):
    for n in range(folders):
        d = os.path.join(root, "G%02d" % (n % groups), "F%03d" % n)
        os.makedirs(d)
        for i in range(files):
            open(os.path.join(d, "P%03d_%03d.FCStd" % (n, i)), "wb").close()


def timed(fn, repeat=5):
    best = None
    for _ in range(repeat):
        t = time.perf_counter()
        result = fn()
        dt = time.perf_counter() - t
        best = dt if best is None else min(best, dt)
    return best, result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folders", type=int, default=200)
    ap.add_argument("--files", type=int, default=18)
    ap.add_argument("--latency-ms", type=float, default=0.0)
    args = ap.parse_args()

    calls = [0]
    real = os.scandir

    def scandir(path="."):
        calls[0] += 1
        if args.latency_ms:
            time.sleep(args.latency_ms / 1000.0)
        return real(path)

    root = tempfile.mkdtemp(prefix="ac_bench_lib_")
    try:
        build_tree(root, args.folders, args.files)
        library.os.scandir = scandir
        folder = os.path.join(root, "G03", "F013")
        group = os.path.join(root, "G03")
        cases = [
            ("Full scan", root, True),
            ("Refresh one folder", folder, False),
            ("Refresh one folder + subfolders (%s)" % os.path.basename(group), group, True),
        ]
        full = library.scan_master(root)
        total = sum(len(v) for v in full.values())
        print("%d files in %d folders, latency %.1f ms per listing"
              % (total, len(full), args.latency_ms))
        print("| Operation | Listings | Scan + merge |")
        print("|---|---|---|")
        for label, path, recursive in cases:
            def run():
                part = library.scan_folder(path, recursive)
                return library.merge_scan(full, path, part, recursive)
            calls[0] = 0
            run()
            n = calls[0]
            dt, _res = timed(run, repeat=1 if args.latency_ms else 5)
            print("| %s | %d | %.1f ms |" % (label, n, dt * 1000))
    finally:
        library.os.scandir = real
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
