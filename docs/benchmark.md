# Large assemblies: BREP versus mesh

Measured with `tools/bench_large.py` in FreeCAD 26.3 (GUI, Linux), on n copies
of one plate with 24 holes (38 BREP faces, 2 746 mesh facets). Each copy holds
its own geometry, like distinct frozen parts (a Link array would share one
display node and hide the cost).

| Representation | Parts | Build | Reopen | Display after reopen | File | Memory after reopen |
|---|---|---|---|---|---|---|
| BREP (`Part::Feature`) | 200 | 14.4 s | 14.0 s | 0.8 s | 1.5 MB | +55 MB |
| BREP (`Part::Feature`) | 400 | 29.1 s | 28.5 s | 1.0 s | 3.0 MB | +26 MB |
| Mesh (`Mesh::Feature`) | 200 | 0.15 s | 0.5 s | 0.7 s | 6.5 MB | +1.5 MB |
| Mesh (`Mesh::Feature`) | 1000 | 0.8 s | 2.9 s | 0.7 s | 32 MB | +33 MB |

## What it shows

* **Opening is the bottleneck, not drawing.** A BREP part costs about 0.07 s
  to reopen (the shapes are restored and tessellated for display); a mesh part
  about 0.003 s, **~24 times less**. Extrapolated to 10 000 parts: about
  12 minutes in BREP, about 30 s in mesh.
* Once open, drawing the view is fast in both cases (under 1 s here).
* The mesh file is larger at this tessellation: meshes have to be decimated
  (fewer facets) for big scenes; the angular deflection, not the linear one,
  drives the facet count of round holes.

## Consequence for Assembly Companion

A "lightweight component" for very large assemblies keeps:

* a small BREP **skeleton**: only the faces / edges / vertices used by joints
  (so the solver and the joints keep working);
* a **mesh skin** for display, decimated;
* a link back to the source file, to open the real part when it has to be
  modified, then refresh the skeleton and the skin.

## Parts library: full scan versus targeted refresh

`tools/bench_library.py` (plain Python) builds a library of 3600 empty
`.FCStd` files in 200 folders (10 groups of 20) and times the scan plus the
merge into the cached result. `--latency-ms` adds a delay to every directory
listing, to mimic a network share (one round trip per listing; on Windows
sizes and dates come with the listing).

| Operation | Listings | Local disk | 5 ms per listing |
|---|---|---|---|
| Full scan | 211 | 11.4 ms | 1175 ms |
| Refresh one folder | 1 | 0.1 ms | 6.1 ms |
| Refresh one group + its 20 folders | 21 | 1.2 ms | 116 ms |

The view gains as much: a full rebuild created one card (and one thumbnail
job) per file, 3600 here; a targeted refresh only recreates the cards of the
refreshed folder (18 here), the other blocks keep their widgets and
thumbnails (checked by `tests/gui/test_explorer_refresh.py`).
