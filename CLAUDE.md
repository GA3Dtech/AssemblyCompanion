# CLAUDE.md – Assembly Companion

FreeCAD workbench (Python, PySide) that works **with** the built-in Assembly
workbench: freezing Links to dead BREP copies, visual parts library, alignment,
selection sets. Not a separate assembly solver. Read `README.md` first;
`docs/README_fr.md` holds the detailed French docs and technical notes.

## Layout

| File | Role |
|---|---|
| `freecad/assembly_companion/init_gui.py` | Workbench class, toolbars, injection into the Assembly workbench |
| `freecad/assembly_companion/commands.py` | Gui commands (thin wrappers that call the modules below) |
| `freecad/assembly_companion/freeze.py` | Freeze / Relink / Delete joints / Diagnostic / Repair |
| `freecad/assembly_companion/explorer.py` | Thumbnail explorer (central tab) and "Insert component (visual)" dock |
| `freecad/assembly_companion/new_part.py` | New part from selection (file PREFIX_001a_Desc, Body + SubShapeBinder) |
| `freecad/assembly_companion/duplicate.py` | Duplicate components (clone Links in the assembly tree) |
| `freecad/assembly_companion/reactivate.py` | Reactivate assembly (clears stale task panel / edit / active-object state) |
| `freecad/assembly_companion/align.py` | Align elements (placement by clicking geometry) |
| `freecad/assembly_companion/selection_sets.py` | Named selection sets stored in the document |
| `freecad/assembly_companion/i18n.py` | `tr()` and language selection |
| `freecad/assembly_companion/prefs.py` | All settings (`get`/`put`) and the preference page |
| `freecad/assembly_companion/translations/` | `<code>.json` tables English → language |
| `tools/i18n.py` | Check / update the translation tables |
| `freecad/assembly_companion/resources/icons/` | SVG icons |
| `package.xml` | Addon Manager metadata (version, date, freecadmin) |

The repository lives directly in the user's FreeCAD `Mod` folder
(`~/.local/share/FreeCAD/v26-3/Mod/AssemblyCompanion`): changes are live after a
FreeCAD restart (or a module reload).

## Language rules (strict)

- **Code comments and docstrings: English only.** Never add French comments.
- **User-facing texts (dialogs, status, console messages): English in the code,
  wrapped in `tr()`**, translated in `translations/<code>.json`.
- Legacy identifiers in `freeze.py` are French (`figer`, `relier`, `copie`,
  `Fige*` properties…). Keep them: they are stored in users' documents
  (`FigeFichier`, `FigeObjet`, group `Solides_figes`…) and renaming breaks
  existing assemblies. New code may use English names.
- Conversation with the user: French.

## Code conventions

- Match the existing style: section banners (`# ----`), short docstrings that
  explain *why*, comment density similar to the surrounding code.
- Every file starts with the `# -*- coding: utf-8 -*-` line, the
  `SPDX-License-Identifier: LGPL-2.1-or-later` line and the license header.
- PySide import pattern: `from PySide import ...` with a `PySide6` fallback.
- Document changes go inside `doc.openTransaction(...)` / `commitTransaction()`
  (one undo step per user action, committed in a `finally`).
- Source files to insert are opened **hidden** (`App.openDocument(path, True)`)
  and their saved shapes are used without recompute.
- `PartDesign::Body` derives from `Part::Feature`: test for Body **before**
  Part::Feature in type checks.
- `Document.RootObjects` is not "the visible top of the tree": any object
  referenced by another one (an App::Link of the same file, a boolean, a
  binder…) is dropped from it. Walk containers and follow same-file Links
  when looking for parts in a file.
- Active assembly: FreeCAD 26.x stores it under the view's active-object key
  `"assembly"`, 1.0 under `"part"`. Always check both (see `ACTIVE_KEYS` in
  `reactivate.py`).
- Toolbar in the Assembly workbench: declared as a custom toolbar in
  `BaseApp/Workbench/AssemblyWorkbench/Toolbar/AssemblyCompanion` (rewritten at
  startup by `init_gui.sync_assembly_toolbar`), so it is a separate, movable
  toolbar. Do not go back to a WorkbenchManipulator: its "append" only adds to
  an existing toolbar and silently ignores unknown toolbar names.
- Settings: always through `prefs.get()` / `prefs.put()` (keys in
  `prefs.DEFAULTS`), and expose new ones on the preference page.
- Translations: user-facing texts are English literals in `tr("...")`,
  formatted after translation with named fields (`.format(name=...)`). After
  changing texts run `python3 tools/i18n.py update`, then fill the new entries
  of `translations/*.json` (fr, de, it, es); `python3 tools/i18n.py check`
  must report nothing missing before a commit.
- A SubShapeBinder that stays linked to the assembly makes the two files depend
  on each other once the new part is inserted ("The graph must be a DAG"):
  new parts default to a detached binder (`BindMode = "Detached"`).
- Must run on FreeCAD 1.0+ (tested on 26.3); Windows network shares are a key
  use case for the explorer (avoid per-file round trips, keep caches).

## Testing

No test suite. Verify logic headless with `freecadcmd` (via the FreeCAD MCP
`execute_code_headless` tool when available): build a small document in the
script, then exec only the functions under test (modules importing PySide /
FreeCADGui may not import headless). GUI behaviour must be checked in FreeCAD by
the user; say so explicitly when it has not been tested.

## Releases and git

- Bump `version` and `date` in `package.xml` for a release, and update the
  status section of `README.md` when features change.
- Update the tool tables in `README.md` (and `docs/README_fr.md` when relevant)
  whenever a command's behaviour changes.
- `__pycache__/` is ignored; never commit it.
- Commit only when the user asks.
