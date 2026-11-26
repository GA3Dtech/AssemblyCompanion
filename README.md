# Assembly Companion

**Workshop-grade tools for FreeCAD's built-in Assembly: durable assemblies, visual parts library, selection sets.**

> [!WARNING]
> **Still experimental: be careful with your files.** Work on copies when the
> files matter, and keep backups. The author cannot be held responsible in
> any case for misuse, transformed or damaged files, or file
> incompatibilities. It is up to each user to test the tools carefully and
> progressively, with their own judgement and for their own needs: what
> worked for someone may not behave the same for you.
>
> Projects made of external links to other files, with joints between the
> parts, are very complex: covering every case takes a lot of time, and the
> successive FreeCAD versions multiply the combinations. The FreeCAD file
> format nevertheless remains, through all this evolution, very stable
> overall — and the very purpose of this workbench is to bring even more
> stability, over the long term.

Assembly Companion is **not another assembly workbench**. It works *with* FreeCAD's built-in Assembly workbench, on its files and its joints, and adds what long-lived, real-world projects need.

## Why

The built-in Assembly workbench links parts from their source files (App::Link). That is light and associative, but every opening recomputes the whole chain: a FreeCAD version change, a moved or renamed file, a small recompute difference, and joints break. Linked parts also have to stay loaded: every source file of the assembly is open at the same time, and the model tree on the left lists every one of them with its whole construction history. Past a handful of parts this becomes an endless tree spread over countless open files, impossible to keep track of — and closing one of these files to tidy up the tree makes its parts vanish from the assembly. A2plus used to store a *dead solid* inside the assembly, so files reopened identically years later and only the assembly itself had to be open. Assembly Companion brings that durability to the built-in workbench, and adds the tools a workshop needs to find, place and select parts in large assemblies.

## Tools

The toolbar and the menu follow the workflow, one group per theme
(separators between groups):

| Group | Commands |
|---|---|
| Library | Local parts explorer, Insert component (visual), Import STEP as part |
| Build | New file, New part from selection, Extract bodies, Update part binder, Duplicate components, Replace component, Selection sets |
| Durable | Freeze parts, Relink to sources, Outdated frozen parts, Check frozen assembly, Delete part joints (menu: Repair) |
| Large assemblies | Make lightweight, Restore full components, Open source file |
| Reports | Bill of materials, Check collisions, Archive |
| Accessories | Check dependencies |
| Finishing | Group fasteners with their body, Align elements, Reactivate assembly |

### Durable assemblies
| Command | What it does |
|---|---|
| **Freeze parts** | Retargets each Link to a dead BREP copy stored in the assembly (no topological history). The assembly no longer depends on source files or on how a future FreeCAD recomputes them. Std_Part containers, imported STEP groups and sub-assemblies (Links or sub-assemblies of the Assembly workbench, any depth) are frozen with their parts, names, placements, colours and internal joints, or optionally as one solid per component. A component whose content cannot be frozen stays linked and is reported; one undo step. |
| **Relink to sources** | Points frozen parts back to their source file, to edit them. Then freeze again. |
| **Delete part joints** | Deletes every joint (and grounding) of the selected parts, in one undo step. |
| **Check frozen assembly** | Reports, for every joint reference, whether it resolves, and on which object and file. |
| *Unused frozen copies* | Frozen copies no part uses any more (part deleted, relinked, replaced) are moved automatically into a **Unused** sub-group of `Solides_figes` and get a crossed-out overlay icon in the tree, so they can be sorted out by hand. Used again, they go back. |
| **Outdated frozen parts** | Lists the frozen parts whose source file was saved after they were frozen (date stored on each copy) and refreezes the checked ones in place from the saved source file, joint references refreshed. |
| **Bill of materials (CSV)** | List of the parts with quantities, flat or by sub-assembly (preference), written to a CSV file: frozen parts under their original name and source file (not `Fige_…`), linked parts, parts stored in the assembly, fasteners, sub-assemblies and Link arrays included. |
| **Archive the assembly** | "Pack and go": the assembly and every file it needs (linked parts, sub-assemblies, optionally the sources of frozen parts) in one zip with a manifest, relative paths kept so it opens anywhere once extracted. Unsaved changes are reported first. |
| **Make lightweight** | For very large assemblies: the selected components (or all) are replaced by a light mesh skin — one per body, colours kept — plus a small BREP skeleton holding only the elements their joints use. Joints and solver keep working, the heavy BREP is no longer in the file (reopening ~24× faster per part, see [docs/benchmark.md](docs/benchmark.md)). |
| *Sub-assemblies and level of detail* | A whole sub-assembly can be made lightweight as one component (its parts, or its own lightweight components, merged into one skin per colour), so a workshop-scale model only loads a few skins. Skins are drawn as boxes when they are small on screen (level of detail chosen by Coin at each frame from the screen area, so it works with the orthographic camera; threshold in the preferences, 0 = always the mesh). |
| **Restore full components** | Puts lightweight components back to the real parts of their source file, joints included; frozen ones are frozen again. |
| **Open source file** | Opens the real file of the selected component (lightweight, frozen or linked) to work on it. |
| **Repair frozen copies** | Cleans copies made by early versions. |
| **Closing a source file** | When a file still used by linked (not frozen) parts of an open assembly is closed — which makes those parts vanish — a warning lists them and offers to freeze them (the file is reopened in the background, the parts are frozen, the file is closed again) or to reopen the file. Can be turned off in the preferences. |
| **Check dependencies** | Explains FreeCAD's question *"The file contains external dependencies. Do you want to save the dependent files, too?"*: lists the files the document depends on (directly or through another file), which are marked modified (often a file opened in the background to read a part), hidden or partially loaded, what changed in them and which objects use them; save them, or ignore their changes. |
| **Reactivate assembly** | Unlocks an assembly that can no longer be activated (Assembly commands greyed out, double-click does nothing): closes a stuck task panel, leaves a pending edit, clears stale active objects, then activates the selected assembly. Reports what it found in the report view. |

Workflow for a modified part: *select it → Relink → edit the source → fix joints → Freeze.*

### Parts library and placement
| Command | What it does |
|---|---|
| **Insert component (visual)** | Large floating window with thumbnails of every FreeCAD file under your parts folder; click to insert into the active assembly / Std_Part. Source files do not need to be open. Optional "freeze on insert". |
| **Duplicate components** | Clones the selected components in the assembly tree: new instances of the same parts (frozen or not), at the same place, with the same colours. Optionally duplicates their joints and grounding too, pointed to the clones (preference: ask / always / never). Source files are not touched. |
| **Update part binder** | Replaces the content of the SubShapeBinder of an open part (made with *New part from selection*) by the faces, edges or parts selected in the assembly, to add or remove context elements. *Shape for TechDraw* of the selection sets likewise updates its binder in place when run again. |
| **Group fasteners with their body** | Moves the screws, nuts, inserts… of the Fasteners workbench into the Std_Part of the body they are attached to, creating a Std_Part around a body that has none. The Part becomes a complete component (inserted and frozen with its fasteners), and the fasteners stay in their holes when the Part is moved — at the document root they drift as soon as the Part is not at the origin. |
| **New part from selection** | Creates a new part file named `PREFIX_001a_Description.FCStd` (working folder, free prefix, next free number proposed, revision, description) whose Body holds a SubShapeBinder of the selected faces, edges or parts — or of a selection set. By default the binder is an independent copy, so the new part can be inserted into the assembly, exactly in place, without making the files depend on each other; a linked binder that follows the assembly is also available. |
| **New file** | Creates a new, empty part file named like the other parts of the project (`PREFIX_NNNr_Description.FCStd`, next free number proposed), by default with a Std_Part container holding an empty Body, both named after the description (names editable, container and Body optional): faster new files, consistent naming. |
| **Extract bodies** | Copies each selected Body with its whole tree (sketches, features, datums, spreadsheets used by its expressions) into its own new file, named like the new parts (`PREFIX_NNNr_<body>.FCStd`): a clean file from a crowded tree. SubShapeBinders become independent and attachments to other objects are removed (placement kept), so the new file stands alone; what still points outside is reported. Optionally replaces the bodies in the assembly by the new parts, joints kept. |
| **Replace component** | Points the selected component to an object of another file — the next revision of its source file (`AB_001a` → `AB_001b`) is proposed automatically, the object with the same internal name is preselected — keeping its place and joints. Frozen components are frozen again from the new file; other instances of the same part can be replaced in the same step. |
| **Import STEP as part** | Imports a STEP file as one Std_Part: the import groups created by FreeCAD's STEP importer become Parts, so every element is visible in the assembly and can carry joints. Saved in a new FreeCAD file next to the assembly (recommended) or created in the assembly document, then inserted into the active assembly. Also from the explorer (STEP files are listed: click or right-click to insert). |
| **Local parts explorer** | Same thumbnail browser in a central tab; click to open. Fast on large network folders (scan and thumbnail cache, background loading). Right-click a folder header to refresh only that folder or to add it to the **favorites** (pinned on top, ★ menu, "Favorites only" filter); right-click a card or a folder to give it a **tag** (emoji or short #tag shown on the thumbnail). Favorites and tags are kept in the user preferences, not in the folders. STEP, STL / 3MF (drawn preview) and PDF files (first page, with poppler's `pdftoppm`) can be shown too ("Also show"). Files saved from FreeCAD refresh their own folder. |
| **Align elements** | Place a body by clicking an element on it, then on another body; flip, offset, rotation, optional gizmo. Ideal for static assemblies in a Std_Part. |
| **Check collisions** | Splits the assembly into elementary parts (through Links, frozen or linked Parts, sub-assemblies) and intersects the pairs whose bounding boxes overlap: interferences are listed (a click selects the two parts) and shown as red volumes. Fasteners can be left out. |
| **Selection sets** | Named selection sets saved in the document: filter by name / size / volume, isolate, transparency, union / intersection / difference, new part from the set. With **Keep faces, edges and vertices** checked, a set stores the chosen elements themselves (marked ◆) and selects them again; **Shape for TechDraw** turns a set into a SubShapeBinder of only those elements, to draw just what matters (no screw threads or cosmetic details). Opening the panel leaves the assembly edit mode so faces, edges and vertices can be picked. Made for exploded STEP files and large assemblies. |

When the built-in **Assembly** workbench is active, the Companion tools are available in a separate **Assembly Companion** toolbar that can be moved, docked anywhere or hidden like any other toolbar.

### Tips and known behaviours

- **Manual placement:** FreeCAD's *Transform* tool (right-click → Transform)
  stays very handy to place a part by hand, also in an assembly of the
  built-in Assembly workbench.
- **Joints on a SubShapeBinder:** with the built-in Assembly workbench, a
  joint between a SubShapeBinder and a part can show an offset in the 3D
  view. It is not a problem for the assembly, only a display effect to be
  aware of.

## Preferences and languages

*Edit → Preferences → Assembly Companion*: interface language, parts library folder, working folder and naming defaults for new parts, binder mode, toolbar in the Assembly workbench, freeze on insert, leaving the assembly edit mode for selection sets, QML or classic panels, full library scan when an explorer opens.

The interface is written in English and translated into **French, German, Italian and Spanish** (by default it follows the language of FreeCAD). Translations are JSON files in `freecad/assembly_companion/translations/`; `python3 tools/i18n.py check` lists missing texts, `python3 tools/i18n.py update` adds them to every file, `python3 tools/i18n.py new <code>` starts a new language. Contributions of new languages are welcome.

## Python API (scripts, macros, addons)

Assembly Companion is a passive workbench: it runs no server, opens no network
connection and starts nothing on its own. `freecad/assembly_companion/api.py`
exposes every tool as a plain Python function for scripts, macros and other
addons: no dialog, the document passed explicitly, JSON-serialisable results,
typed errors (`errors.py`) and `dry_run=True` on the functions that change a
document. `api.describe()` returns the catalogue; the reference is
[docs/api.md](docs/api.md).

In the FreeCAD Python console or a macro:

```python
from freecad.assembly_companion import api
print(api.list_components("Assembly"))
print(api.freeze_parts("Assembly", dry_run=True))   # what would be frozen
print(api.diagnose("Assembly")["broken"])
```

Batch on a file without the GUI (`freecadcmd`): bill of materials,
collisions, archive, diagnostic.

```python
import FreeCAD as App
from freecad.assembly_companion import api
doc = App.openDocument("/path/to/assembly.FCStd")
api.export_bom_csv(doc, "/path/to/assembly_BOM.csv")
print(api.check_collisions(doc))
print(api.diagnose(doc)["broken"])
api.archive(doc, "/path/to/assembly_pack.zip")
App.closeDocument(doc.Name)
```

## Tests

Four levels, all run by the GitHub Actions CI with real FreeCAD builds
(1.1.4, 26.3 and the latest weekly development build):

| Level | Folder | Runs in | What |
|---|---|---|---|
| unit | `tests/unit` | plain Python (FreeCAD stand-ins) | naming, CSV, preferences, translations, library scan, panel models, API reference |
| freecad | `tests/freecad` | `freecadcmd` | every tool through `api.py` on generated fixture files |
| vanilla | `tests/vanilla` | `freecadcmd` without the addon | files made by the workbench open and solve in a plain FreeCAD, and with the 0.1.0 code |
| gui | `tests/gui` | FreeCAD GUI (xvfb in CI) | workbench, commands, explorer refresh, QML panels and their widgets fallback |

```bash
tests/run_all.sh unit
```

`tests/run_all.sh freecad`, `vanilla` and `all` use a FreeCAD AppImage
(`FREECAD_APPIMAGE`) with an isolated user folder. Fixture files are rebuilt
by `tests/fixtures/build_fixtures.py`; `tests/fixtures/legacy/` keeps files
made by released versions, which must keep opening.

## Installation

Until it is listed in the Addon Manager: *Edit → Preferences → Addon Manager → Custom repositories*, add `https://github.com/GA3Dtech/AssemblyCompanion` (branch `main`), then install **Assembly Companion** from the Addon Manager and restart FreeCAD.

Manual install: copy this folder into your FreeCAD `Mod` directory.

Requires FreeCAD 1.1 or newer.

## Status

Version 0.2.0 – sub-assemblies and STEP groups frozen, STEP import as part, body extraction, explorer favorites and configurable cache, generic panels, public Python API and automatic tests on FreeCAD 1.1.4, 26.3 and the weekly build. Detailed French documentation and technical notes: [docs/README_fr.md](docs/README_fr.md).

Every function is covered by the automatic tests (FreeCAD 1.1.4, 26.3 and the weekly build). **Stable** functions are used on real projects; **experimental** ones are new: tested, but not yet proven in daily work — check the result and report problems.

| Function | Status |
|---|---|
| Freeze / relink parts and Std_Parts, check frozen assembly, repair, delete part joints | stable |
| Outdated frozen parts, bill of materials (flat), archive, replace component, check collisions | stable |
| Insert component (visual), local explorer (targeted refresh, cache), new part from selection, update part binder | stable |
| Duplicate components (joints included), group fasteners, align elements, selection sets, reactivate assembly | stable |
| Lightweight components (skeleton + mesh skins, level of detail) | stable |
| Freeze sub-assemblies and imported STEP groups, "one solid per component" mode | experimental |
| Bill of materials by sub-assembly (hierarchical) | experimental |
| Import STEP as part | experimental |
| Extract bodies, new file | experimental |
| Explorer favorites and tags, configurable cache folder | experimental |
| QML panels (generic panels with widgets fallback) | experimental |

## Releases

`main` is the development branch; stable versions are published from the `release` branch, each with a new version and date in `package.xml` and a section in `CHANGELOG.md` (see [docs/RELEASING.md](docs/RELEASING.md)).

## Credits and license

Code taken from other projects, credited in the headers of the files that use it:

| Project | Authors | License | Used in |
|---|---|---|---|
| [PiStock](https://github.com/pistock-org/PiStock) – local explorer | GA3Dtech | LGPL-2.1-or-later (relicensed by its author for this project) | `explorer.py` |
| [ShowRoom](https://github.com/oficinerobotica/ShowRoom) – `dtpanels` (bridge, widget form, theme) | OficineRobotica | LGPL-2.1-or-later | `panel_model.py`, `bridge.py`, `qml_host.py`, `resources/qml/` |
| [FreeCAD-Nxt](https://github.com/obelisk79/FreeCAD-Nxt) – `quick_host`, `qtquick` | obelisk79 | LGPL-2.1-or-later | `qml_host.py` |

Licensed under the **LGPL-2.1-or-later**, like FreeCAD itself. No CLA: contributions are welcome under the same license.

### Spirit of the project

This is first of all a free sharing of my own tools. FreeCAD developers, forks and any related project are welcome to take whatever they like from it: a mention of where it comes from, in the code comments, is all I ask.

The goal is not to start a debate or to get everyone to agree on the best way of working. These tools are tuned to the way I work. If you want to work the same way or take inspiration from it, help yourself. If it does not suit you, I am always curious to learn better ways of doing things — but unless there is something concrete to bring, I will not debate it much further.

### About the use of AI

An AI coding agent is used to write this workbench. That does not make it untested: every tool comes from a real need in the workshop, is tested on real projects, and goes through many iterations before it is kept, which in the end gives code of good quality. If this bothers you, thank you for not reporting it — it brings nothing, and it does not stop anyone from borrowing the good ideas for other projects.
