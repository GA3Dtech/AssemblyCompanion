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
| `freecad/assembly_companion/fasteners.py` | Group Fasteners workbench parts into the Std_Part of their body |
| `freecad/assembly_companion/new_part.py` | New part from selection (file PREFIX_001a_Desc, Body + SubShapeBinder) |
| `freecad/assembly_companion/outdated.py` | Outdated frozen parts: compare FigeDate with the source file, refreeze |
| `freecad/assembly_companion/bom.py` | Bill of materials (CSV), frozen parts under their original name |
| `freecad/assembly_companion/replace.py` | Replace a component by another file / revision, joints kept |
| `freecad/assembly_companion/archive.py` | Pack and go: assembly + needed files in a zip |
| `freecad/assembly_companion/collisions.py` | Interference check between parts (Shape.common), red result object |
| `freecad/assembly_companion/lightweight.py` | Lightweight components (skeleton BREP + mesh skins), restore, open source |
| `freecad/assembly_companion/duplicate.py` | Duplicate components (clone Links in the assembly tree) |
| `freecad/assembly_companion/reactivate.py` | Reactivate assembly (clears stale task panel / edit / active-object state) |
| `freecad/assembly_companion/align.py` | Align elements (placement by clicking geometry) |
| `freecad/assembly_companion/selection_sets.py` | Named selection sets stored in the document |
| `freecad/assembly_companion/close_guard.py` | Document observer: warn / freeze when a linked source file is closed |
| `freecad/assembly_companion/docs.py` | Open source files without changing the active document |
| `freecad/assembly_companion/i18n.py` | `tr()` and language selection |
| `freecad/assembly_companion/prefs.py` | All settings (`get`/`put`) and the preference page |
| `freecad/assembly_companion/api.py` | Public API for scripts, agents and MCP (headless-safe, JSON results); reference `docs/api.md` |
| `freecad/assembly_companion/errors.py` | Typed exceptions of the API |
| `freecad/assembly_companion/version.py` | Version read from `package.xml` (single source) |
| `freecad/assembly_companion/library.py` | Parts library scan (no Qt): `scan_folder`, `merge_scan`, disk caches |
| `freecad/assembly_companion/panel_model.py` | Panel models (no Qt): typed parameters, sections, actions |
| `freecad/assembly_companion/bridge.py` | Generic panels: Bridge to the QML, `WidgetForm` fallback, `PanelDialog` / `show_panel` |
| `freecad/assembly_companion/qml_host.py` | Qt Quick import, OpenGL graphics API, `make_view`, QML or widgets choice |
| `freecad/assembly_companion/resources/qml/` | Generic QML components (`GenericPanel`, `Section`, one row per parameter kind) |
| `freecad/assembly_companion/translations/` | `<code>.json` tables English → language |
| `tools/i18n.py` | Check / update the translation tables |
| `tools/bench_large.py` | Benchmark of very large assemblies, BREP vs mesh (results in `docs/benchmark.md`) |
| `tools/bench_library.py` | Benchmark of the library scan, full vs targeted refresh |
| `tools/api_doc.py` | Writes / checks `docs/api.md` from `api.describe()` |
| `tests/` | `unit`, `freecad`, `vanilla`, `gui`, fixtures, CI helpers (see Testing) |
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
- Source files are opened with `docs.open_source(path, keep=assembly_doc)` only,
  never `App.openDocument` directly: opening a document (even hidden) makes it
  the ACTIVE document, which greys out every Assembly command and locks the
  assembly. Their saved shapes are used without recompute.
- Read the active assembly from `Gui.getDocument(doc.Name).ActiveView`, not from
  `Gui.ActiveDocument` (the active document may be another one).
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
- FreeCAD detaches cross-document Links BEFORE `slotDeletedDocument`: their target
  cannot be read there (close_guard keeps the last known target of each Link).
- The FreeCAD MCP server (`mcp__freecad__execute_code`) can drive the user's open
  FreeCAD: test GUI behaviour there on COPIES of files (temporary folder), never
  on the user's open documents, and close the copies afterwards.
- Lightweight components must not keep any live link (XLink, Link) to the heavy
  original, or FreeCAD loads its BREP anyway: only text references (LWFile,
  LWObject, LWMap in source names). Child names are unique per document
  (Skeleton, Skeleton001…): never write them literally in subnames.
- Level of detail: use `SoLevelOfDetail` (projected screen area), not `SoLOD`
  (camera distance): FreeCAD's default camera is orthographic, zooming does not
  change the distance. LOD skins are `App::FeaturePython` + `Mesh::PropertyMeshKernel`
  with a Python view provider; a `Mesh::FeaturePython` brings the native mesh view
  provider, which does not handle a custom display mode.
- MCP screenshots refit the view: to check what a zoom level shows, use
  `ActiveView.saveImage(path, w, h, "Current")` and read the image.
- Must run on FreeCAD 1.1+ (tested on 1.1 and 26.3); Windows network shares are a key
  use case for the explorer (avoid per-file round trips, keep caches).

## Panels (generic model, QML or widgets)

- A form panel (options, lists, actions) is a model in `panel_model.py`
  terms, shown by `bridge.show_panel(model)`: QML when the `UseQmlPanels`
  preference is on and Qt Quick can use OpenGL, otherwise a `WidgetForm`
  built from the same model. **Never write a panel twice by hand**; when the
  engine lacks something, add a parameter kind to the engine (model, Bridge,
  WidgetForm and a QML row together).
- No business logic in the QML, the widgets or the bridge: the model's
  actions call `api.py`. The model does not touch the document while the
  panel is open; the accept action makes one API call (one undo step),
  Cancel changes nothing.
- Custom QML only where widgets are clearly worse (long thumbnail grids,
  overlays on the 3D view), justified in one line in the docstring, with a
  simpler fallback that keeps the function.
- Hand-built widget panels left are listed with their reason in
  `tests/unit/test_panel_review.py`; migrating one removes its entry.
- QML pitfalls: import Qt Quick lazily from PySide6 / PySide2 (FreeCAD's
  `PySide` has no QtQuick); ask for OpenGL before the first QQuickWidget
  (`qml_host.quick_usable`); versioned imports `import QtQuick 2.15` (Qt 5
  and Qt 6); no QML Popup (Wayland offset); the bridge is parented to the
  view; never resize the view from a QML binding (QTimer at 0 ms); texts
  through `i18n.tr("...")`, never `qsTr` (`tools/i18n.py` scans `.qml`).
  Items created by a `Loader` have no QObject parent: tests walk
  `childItems()` instead of `findChild`.

## Testing

Every logic change comes with tests at the right level. Levels:

- `tests/unit` – plain Python with FreeCAD stand-ins (`tests/unit/conftest.py`):
  `uvx --with pytest pytest -q tests/unit` (or `tests/run_all.sh unit`).
- `tests/freecad` – inside `freecadcmd`, through `api.py`, on fixtures built
  by `tests/fixtures/build_fixtures.py`: `tests/run_all.sh freecad`
  (`FREECAD_APPIMAGE` selects the build; an isolated `FREECAD_USER_HOME` with
  the repo linked into `Mod`).
- `tests/vanilla` – files made by the workbench must open, keep their
  geometry and solve **in a FreeCAD without the addon**, and open with the
  0.1.0 code. Any new stored object or property must keep that true (only
  data proxies may be missing); otherwise mark the test `xfail` with the
  reason and ask the user before changing the stored format.
- `tests/gui` – inside the FreeCAD GUI: xvfb in CI; locally through the
  MCP `execute_code` (pytest from `~/.cache/ac_tests/pytest-py313` on
  `sys.path`, reload the changed modules, delete `test_*` / `conftest*`
  from `sys.modules` before each run, restore any preference a test or
  script changes, e.g. `LocalMasterDir`).
- `python3 tools/i18n.py check` and `python3 tools/api_doc.py --check` must
  pass; the CI (`.github/workflows/ci.yml`) runs everything on FreeCAD 1.1.4,
  26.3 and the latest weekly build (allowed to fail: early warning).
- freecadcmd pitfalls: scripts run with `__name__` = file stem, need an
  absolute path, must flush stdout before `os._exit`, and may exit 0 on
  failure (check the JUnit report: `tests/ci/check_junit.py`).

GUI behaviour not covered by `tests/gui` must be checked in FreeCAD by the
user; say so explicitly when it has not been tested.

## Releases and git

- Bump `version` and `date` in `package.xml` for a release, and update the
  status section of `README.md` when features change.
- Update the tool tables in `README.md` (and `docs/README_fr.md` when relevant)
  whenever a command's behaviour changes.
- `__pycache__/` is ignored; never commit it.
- Commit only when the user asks.
