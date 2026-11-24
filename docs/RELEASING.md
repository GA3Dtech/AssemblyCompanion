# Releasing Assembly Companion

Two branches:

* `main` – development: every change arrives through a pull request whose
  CI is green (FreeCAD 1.1.4, 26.3 and the weekly build, the weekly being
  allowed to fail);
* `release` – stable: what the Addon Manager installs. It only moves
  forward by merging `main` at a release.

## Making a release

1. On `main`, check that the CI is green and that the functions marked
   *experimental* in the README status table are the ones you mean.
2. Bump `version` (semantic: `0.2.0`) and `date` (`YYYY-MM-DD`) in
   `package.xml`; move the `[Unreleased]` section of `CHANGELOG.md` under
   the new version and date; update the status section of `README.md`.
3. Commit ("Release 0.2.0"), push, wait for the CI.
4. Merge `main` into `release` (fast-forward), tag it `v0.2.0`, push the
   branch and the tag; create the GitHub release from the tag with the
   changelog section as text.

The Addon Index entry of the workbench points to the `release` branch, so
users only get tested versions; `main` can be installed by hand for
testing.
