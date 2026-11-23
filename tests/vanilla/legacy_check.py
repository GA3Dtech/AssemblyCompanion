# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
tests/vanilla/legacy_check.py - run by a FreeCAD whose Mod folder holds the
OLD addon (version 0.1.0): opens the files of $AC_VANILLA_FILES with it and
runs its diagnostic, to check that it ignores what it does not know.
Report in $AC_VANILLA_OUT: {path: {"broken": n | None, "error": str | None}}.
"""

import json
import os
import sys

report = {}
try:
    import FreeCAD as App
    from freecad.assembly_companion import freeze
    report["_addon"] = freeze.__file__
    for path in json.loads(os.environ["AC_VANILLA_FILES"]):
        entry = {"broken": None, "error": None}
        try:
            doc = App.openDocument(path)
            doc.recompute()
            entry["broken"] = freeze.diagnostic(doc)
        except Exception as e:
            entry["error"] = repr(e)
        report[path] = entry
        for name in list(App.listDocuments()):
            App.closeDocument(name)
except Exception:
    import traceback
    report["_fatal"] = traceback.format_exc()
with open(os.environ["AC_VANILLA_OUT"], "w") as fh:
    json.dump(report, fh, indent=1)
sys.stdout.flush()
os._exit(0)
