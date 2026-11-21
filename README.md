# Assembly Companion

**Workshop-grade tools for FreeCAD's built-in Assembly: durable assemblies, visual parts library, selection sets.**

Assembly Companion is **not another assembly workbench**. It works *with* FreeCAD's built-in Assembly workbench, on its files and its joints, and adds what long-lived, real-world projects need.

## Why

The built-in Assembly workbench links parts from their source files (App::Link). That is light and associative, but every opening recomputes the whole chain: a FreeCAD version change, a moved or renamed file, a small recompute difference, and joints break. A2plus used to store a *dead solid* inside the assembly, so files reopened identically years later. Assembly Companion brings that durability to the built-in workbench, and adds the tools a workshop needs to find, place and select parts in large assemblies.

## Tools

### Durable assemblies
| Command | What it does |
|---|---|
| **Freeze parts** | Retargets each Link to a dead BREP copy stored in the assembly (no topological history). The assembly no longer depends on source files or on how a future FreeCAD recomputes them. Links to a Std_Part container get a frozen Std_Part holding a dead copy of each Body, joints included. |
| **Relink to sources** | Points frozen parts back to their source file, to edit them. Then freeze again. |
| **Delete part joints** | Deletes every joint (and grounding) of the selected parts, in one undo step. |
| **Check frozen assembly** | Reports, for every joint reference, whether it resolves, and on which object and file. |
| **Repair frozen copies** | Cleans copies made by early versions. |
| **Reactivate assembly** | Unlocks an assembly that can no longer be activated (Assembly commands greyed out, double-click does nothing): closes a stuck task panel, leaves a pending edit, clears stale active objects, then activates the selected assembly. Reports what it found in the report view. |

Workflow for a modified part: *select it → Relink → edit the source → fix joints → Freeze.*

### Parts library and placement
| Command | What it does |
|---|---|
| **Insert component (visual)** | Dock with thumbnails of every FreeCAD file under your parts folder; click to insert into the active assembly / Std_Part. Source files do not need to be open. Optional "freeze on insert". |
| **Duplicate components** | Clones the selected components in the assembly tree: new instances of the same parts (frozen or not), at the same place, with the same colours, without joints. Source files are not touched. |
| **New part from selection** | Creates a new part file named `PREFIX_001a_Description.FCStd` (working folder, free prefix, next free number proposed, revision, description) whose Body holds a SubShapeBinder of the selected faces, edges or parts — or of a selection set. By default the binder is an independent copy, so the new part can be inserted into the assembly, exactly in place, without making the files depend on each other; a linked binder that follows the assembly is also available. |
| **Local parts explorer** | Same thumbnail browser in a central tab; click to open. Fast on large network folders (scan and thumbnail cache, background loading). |
| **Align elements** | Place a body by clicking an element on it, then on another body; flip, offset, rotation, optional gizmo. Ideal for static assemblies in a Std_Part. |
| **Selection sets** | Named selection sets saved in the document: filter by name / size / volume, isolate, transparency, union / intersection / difference, new part from the set. Opening the panel leaves the assembly edit mode so faces, edges and vertices can be picked. Made for exploded STEP files and large assemblies. |

When the built-in **Assembly** workbench is active, the Companion tools are available in a separate **Assembly Companion** toolbar that can be moved, docked anywhere or hidden like any other toolbar.

## Preferences and languages

*Edit → Preferences → Assembly Companion*: interface language, parts library folder, working folder and naming defaults for new parts, binder mode, toolbar in the Assembly workbench, freeze on insert, leaving the assembly edit mode for selection sets.

The interface is written in English and translated into **French, German, Italian and Spanish** (by default it follows the language of FreeCAD). Translations are JSON files in `freecad/assembly_companion/translations/`; `python3 tools/i18n.py check` lists missing texts, `python3 tools/i18n.py update` adds them to every file, `python3 tools/i18n.py new <code>` starts a new language. Contributions of new languages are welcome.

## Installation

Until it is listed in the Addon Manager: *Edit → Preferences → Addon Manager → Custom repositories*, add `https://github.com/GA3Dtech/AssemblyCompanion` (branch `main`), then install **Assembly Companion** from the Addon Manager and restart FreeCAD.

Manual install: copy this folder into your FreeCAD `Mod` directory.

Requires FreeCAD 1.0 or newer.

## Status

Version 0.1.0 – first workbench release of tools used and tested on FreeCAD 26.3rc2. Detailed French documentation and technical notes: [docs/README_fr.md](docs/README_fr.md).

## Credits and license

The local explorer is derived from [PiStock](https://github.com/pistock-org/PiStock) (© GA3Dtech).

Licensed under the **LGPL-2.1-or-later**, like FreeCAD itself. No CLA: contributions are welcome under the same license.
