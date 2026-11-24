# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
tools/bench_large.py (Assembly Companion) - measure how FreeCAD copes with a
very large assembly, BREP versus mesh.

Run inside FreeCAD (Python console or macro):

    exec(open("<repo>/tools/bench_large.py").read())
    bench(n=500, mode="brep")      # frozen-like BREP copies (Part::Feature)
    bench(n=500, mode="mesh")      # mesh skins (Mesh::Feature)

Builds n copies of one detailed part (a plate with 24 holes) on a grid inside a Std_Part, each copy holding its OWN geometry
like distinct frozen parts (a Link array would share one display node and
hide the cost). Reports: build time, file size, reopen time, time to the
first display, memory, triangles. Files go to a temporary folder and are
deleted afterwards; each result is also appended to
<temp>/ac_bench_results.txt.
"""

import os
import time
import shutil
import tempfile

import FreeCAD as App


def _rss_mb():
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return float("nan")


def detailed_part():
    """Plate 80 x 50 x 10 with 24 holes (fillets when OCCT accepts them)."""
    import Part
    plate = Part.makeBox(80, 50, 10)
    holes = [Part.makeCylinder(2.5, 12, App.Vector(8 + 13 * i, 8 + 11 * j, -1))
             for i in range(6) for j in range(4)]
    s = plate.cut(Part.makeCompound(holes))
    try:
        s = s.makeFillet(1.0, [e for e in s.Edges if e.BoundBox.ZLength == 0 and
                               e.Curve.__class__.__name__ == "Line"][:12])
    except Exception:
        pass
    return s


def _display(doc):
    """Seconds until the 3D view has drawn the document (GUI only)."""
    if not App.GuiUp:
        return float("nan")
    import FreeCADGui as Gui
    t = time.time()
    gdoc = Gui.getDocument(doc.Name)
    gdoc.ActiveView.viewIsometric()
    gdoc.ActiveView.fitAll()
    Gui.updateGui()
    return time.time() - t


def bench(n=500, mode="brep", deflection=0.2, keep=False):
    """Build, save, reopen and display n parts; print and return the figures."""
    import Part
    import Mesh
    import MeshPart
    folder = tempfile.mkdtemp(prefix="ac_bench_")
    path = os.path.join(folder, "bench_%s_%d.FCStd" % (mode, n))
    shape = detailed_part()
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=deflection,
                                  AngularDeflection=0.5, Relative=False)
    side = int(n ** 0.5) + 1
    rss0 = _rss_mb()

    t = time.time()
    doc = App.newDocument("Bench_%s_%d" % (mode, n))
    root = doc.addObject("App::Part", "Workshop")
    for i in range(n):
        pl = App.Placement(App.Vector(100 * (i % side), 70 * (i // side), 0), App.Rotation())
        if mode == "mesh":
            o = doc.addObject("Mesh::Feature", "Skin")
            m = mesh.copy()
            m.Placement = pl
            o.Mesh = m
        else:
            o = doc.addObject("Part::Feature", "Copy")
            s = shape.copy()
            s.Placement = pl
            o.Shape = s
        root.addObject(o)
    doc.recompute()
    t_build = time.time() - t
    t_disp1 = _display(doc)

    t = time.time()
    doc.saveAs(path)
    t_save = time.time() - t
    size = os.path.getsize(path) / 1e6
    App.closeDocument(doc.Name)

    rss1 = _rss_mb()
    t = time.time()
    doc = App.openDocument(path)
    t_open = time.time() - t
    t_disp2 = _display(doc)
    rss2 = _rss_mb()
    App.closeDocument(doc.Name)
    if not keep:
        shutil.rmtree(folder, ignore_errors=True)

    res = {
        "mode": mode, "n": n,
        "faces_or_facets_per_part": len(shape.Faces) if mode == "brep" else mesh.CountFacets,
        "build_s": round(t_build, 2), "first_display_s": round(t_disp1, 2),
        "save_s": round(t_save, 2), "file_MB": round(size, 1),
        "reopen_s": round(t_open, 2), "display_after_reopen_s": round(t_disp2, 2),
        "memory_MB_after_reopen": round(rss2 - rss1, 1),
        "memory_MB_build": round(rss1 - rss0, 1),
    }
    App.Console.PrintMessage("bench %r\n" % res)
    # Also appended to a file: long runs outlive remote calls
    try:
        with open(os.path.join(tempfile.gettempdir(), "ac_bench_results.txt"), "a") as fh:
            fh.write(repr(res) + "\n")
    except Exception:
        pass
    return res
