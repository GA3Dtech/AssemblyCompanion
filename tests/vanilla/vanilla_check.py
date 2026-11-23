# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
tests/vanilla/vanilla_check.py - run by a FreeCAD WITHOUT any addon (empty
FREECAD_USER_HOME, repository not on sys.path). Opens every file listed in
$AC_VANILLA_FILES (JSON list) and writes a JSON report to $AC_VANILLA_OUT:
  {"addon_importable": bool, "files": {path: {"objects": {...},
   "assemblies": {...}, "broken_refs": [...], "error": str|None}}}
"""

import json
import os
import sys

report = {"addon_importable": True, "files": {}}
try:
    import FreeCAD as App
    try:
        import freecad.assembly_companion  # noqa: F401
    except ImportError:
        report["addon_importable"] = False
    for path in json.loads(os.environ["AC_VANILLA_FILES"]):
        entry = {"objects": {}, "assemblies": {}, "broken_refs": [], "error": None}
        report["files"][path] = entry
        try:
            doc = App.openDocument(path)
            doc.recompute()
            for o in doc.Objects:
                info = {"type": o.TypeId, "invalid": "Invalid" in o.State}
                if "Proxy" in o.PropertiesList:
                    p = o.Proxy
                    info["proxy"] = None if p is None else type(p).__module__ + "." + \
                        type(p).__name__
                if hasattr(o, "Shape") and not o.isDerivedFrom("App::Link"):
                    try:
                        info["null"] = o.Shape.isNull()
                        info["volume"] = round(o.Shape.Volume, 4) if not o.Shape.isNull() else 0
                    except Exception as e:
                        info["shape_error"] = str(e)
                if "Mesh" in o.PropertiesList:
                    try:
                        info["facets"] = o.Mesh.CountFacets
                    except Exception:
                        info["facets"] = -1
                entry["objects"][o.Name] = info
                if hasattr(o, "JointType") or "ObjectToGround" in o.PropertiesList:
                    for prop in ("Reference1", "Reference2"):
                        v = getattr(o, prop, None)
                        if not v:
                            continue
                        for sub in v[1]:
                            try:
                                ok = v[0].getSubObject(sub) is not None
                            except Exception:
                                ok = False
                            if not ok:
                                entry["broken_refs"].append("%s.%s:%s" % (o.Name, prop, sub))
            for o in doc.Objects:
                if o.isDerivedFrom("Assembly::AssemblyObject"):
                    try:
                        entry["assemblies"][o.Name] = int(o.solve())
                    except Exception as e:
                        entry["assemblies"][o.Name] = str(e)
        except Exception as e:
            entry["error"] = repr(e)
        for name in list(App.listDocuments()):
            App.closeDocument(name)
except Exception:
    import traceback
    report["fatal"] = traceback.format_exc()
with open(os.environ["AC_VANILLA_OUT"], "w") as fh:
    json.dump(report, fh, indent=1)
sys.stdout.flush()
os._exit(0)
