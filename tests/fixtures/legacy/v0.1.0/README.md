# Legacy fixtures – Assembly Companion 0.1.0

Frozen reference files: they prove that assemblies made with this version of
the addon still open with later versions. **Never regenerate them**: they can
only be produced by the code of this version.

- Addon: Assembly Companion 0.1.0 (`package.xml`), code of commit
  `c1eb5c1` (branch `quality/tests-api-ci`; same behaviour as `3e793b6` on
  `main`, only lint comments added).
- FreeCAD: 26.3.0 RC1 (`26.3.0RC1R20261008`, AppImage, Linux x86_64), headless
  `freecadcmd`.
- Generator: `tests/fixtures/build_fixtures.py` (`build_all(out, states=True)`).
- Built on 2026-11-23.

| Folder | Content |
|---|---|
| `basic/` | plate (hole r5), pin, block + assembly: plate grounded, Revolute pin, Fixed block |
| `std_part/` | Std_Part "Cotes" with two Bodies linked into an assembly, Fixed through the Part path |
| `subassembly/` | sub-assembly inserted into a main assembly next to a grounded base |
| `collisions/` | boxes A, B (overlap 500 mm³), C touching B only |
| `revisions/` | AB_001a_Plate / AB_001b_Plate and an assembly on revision a |
| `link_array/` | Link array of 4 bolts + 1 single bolt |
| `state_frozen/` | basic/ after Freeze parts |
| `state_std_part_frozen/` | std_part/ after Freeze parts (frozen Std_Part) |
| `state_lightweight/` | basic/ after Make lightweight (LOD skins, default preferences) |
| `state_selection_sets/` | basic/ with two selection sets (parts, and faces / edges) |
| `state_duplicated_joints/` | basic/ after Duplicate components (Pin) with its joints |

Checked when built: every joint reference resolves, no invalid object.
