# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Every file produced by the addon must open in a FreeCAD WITHOUT any addon:
the addon's own behaviour may be lost, never the geometry nor the
resolution of the assembly.

Run inside FreeCAD with the addon (tests/run_in_freecad.py): the files are
produced here, then a second freecadcmd with an empty user home and the
repository off sys.path opens them (tests/vanilla/vanilla_check.py).
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

try:
    import FreeCAD as App
except ImportError:
    App = None

pytestmark = [pytest.mark.vanilla, pytest.mark.freecad]

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(HERE)
LEGACY = os.path.join(TESTS, "fixtures", "legacy")

# Python objects of the addon whose class is missing without it: allowed,
# they only hold data (selection sets) or display data (lightweight skins)
ALLOWED_MISSING_PROXY = ("SelectionSetMembers", "LodPixels")


def _freecadcmd():
    exe = os.environ.get("AC_FREECADCMD")
    if exe:
        return exe
    for a in (sys.executable, sys.argv[0] if sys.argv else ""):
        if a and os.path.basename(a).lower().startswith("freecadcmd"):
            return a
    return shutil.which("freecadcmd") or shutil.which("FreeCADCmd")


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    """Files produced by the current code (fixtures + addon states), plus
    the legacy files, and the reference volumes measured with the addon."""
    if App is None:
        pytest.skip("needs FreeCAD")
    sys.path.insert(0, os.path.join(TESTS, "fixtures"))
    import build_fixtures
    root = str(tmp_path_factory.mktemp("produced"))
    build_fixtures.build_all(root, states=True)
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    legacy = str(tmp_path_factory.mktemp("legacy"))
    if os.path.isdir(LEGACY):
        shutil.copytree(LEGACY, legacy, dirs_exist_ok=True)
    files = sorted(glob.glob(root + "/*/*.FCStd") + glob.glob(legacy + "/*/*/*.FCStd"))
    reference = {}
    for f in files:
        d = App.openDocument(f)
        reference[f] = {o.Name: round(o.Shape.Volume, 4) for o in d.Objects
                        if hasattr(o, "Shape") and not o.isDerivedFrom("App::Link")
                        and not o.Shape.isNull()}
        for name in list(App.listDocuments()):
            App.closeDocument(name)
    return files, reference


@pytest.fixture(scope="module")
def vanilla_report(produced):
    exe = _freecadcmd()
    if not exe:
        pytest.skip("freecadcmd not found (set AC_FREECADCMD)")
    files, _ref = produced
    home = tempfile.mkdtemp(prefix="ac_vanilla_home_")
    out = os.path.join(home, "report.json")
    env = dict(os.environ)
    env.update(FREECAD_USER_HOME=home, AC_VANILLA_FILES=json.dumps(files), AC_VANILLA_OUT=out)
    env.pop("PYTHONPATH", None)
    subprocess.run([exe, os.path.join(HERE, "vanilla_check.py")], env=env, timeout=900,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with open(out) as fh:
        report = json.load(fh)
    shutil.rmtree(home, ignore_errors=True)
    assert "fatal" not in report, report.get("fatal")
    return report


def test_addon_really_absent(vanilla_report):
    assert vanilla_report["addon_importable"] is False


def test_every_file_opens(vanilla_report):
    errors = {f: e["error"] for f, e in vanilla_report["files"].items() if e["error"]}
    assert not errors


def test_geometry_kept(vanilla_report, produced):
    _files, reference = produced
    problems = []
    for f, entry in vanilla_report["files"].items():
        for name, vol in reference[f].items():
            o = entry["objects"].get(name)
            if o is None or o.get("null") or abs(o.get("volume", 0) - vol) > 1e-3:
                problems.append("%s: %s" % (os.path.basename(os.path.dirname(f)), name))
            if o is not None and o["invalid"]:
                problems.append("%s: %s invalid" % (os.path.basename(f), name))
    assert not problems


def test_assemblies_resolve(vanilla_report):
    bad = {}
    for f, entry in vanilla_report["files"].items():
        for asm, code in entry["assemblies"].items():
            if code != 0:
                bad[f + ":" + asm] = code
        if entry["broken_refs"]:
            bad[f] = entry["broken_refs"]
    assert not bad


def test_only_expected_proxies_missing(vanilla_report, produced):
    """Duplicated joints must use the built-in Assembly classes; only data
    objects of the addon may lose their class."""
    unexpected = []
    for f, entry in vanilla_report["files"].items():
        for name, o in entry["objects"].items():
            if "proxy" in o and o["proxy"] is None:
                d = App.openDocument(f)
                props = d.getObject(name).PropertiesList
                for n in list(App.listDocuments()):
                    App.closeDocument(n)
                if not any(p in props for p in ALLOWED_MISSING_PROXY):
                    unexpected.append("%s: %s" % (os.path.basename(f), name))
    assert not unexpected


@pytest.mark.xfail(reason="LOD skins are App::FeaturePython with a Python view provider: "
                          "without the addon their mesh is kept but NOT displayed "
                          "(skeletons only). Proposed fix in the report: also store a "
                          "native Mesh::Feature, needs a format decision.", strict=False)
def test_lightweight_skins_displayable_without_addon(vanilla_report):
    for f, entry in vanilla_report["files"].items():
        for name, o in entry["objects"].items():
            if o["type"] == "App::FeaturePython" and o.get("facets", 0) > 0 and \
                    o.get("proxy") is None:
                pytest.fail("skin %s of %s has no view provider without the addon" % (name, f))


LEGACY_COMMIT = "3e793b6"       # last commit of version 0.1.0 on main


def test_current_files_open_with_legacy_code(produced, tmp_path):
    """Files written by the current code open with the 0.1.0 addon, whose
    diagnostic finds no broken reference (unknown objects are ignored)."""
    exe = _freecadcmd()
    root = os.path.dirname(TESTS)
    if not exe or not shutil.which("git") or not os.path.isdir(os.path.join(root, ".git")):
        pytest.skip("needs freecadcmd and the git history")
    files = [f for f in produced[0] if "legacy" not in f and f.endswith("assembly.FCStd")]
    home = str(tmp_path / "home")
    mod = os.path.join(home, "Mod", "AssemblyCompanion")
    os.makedirs(mod)
    archive = subprocess.run(["git", "-C", root, "archive", LEGACY_COMMIT],
                             stdout=subprocess.PIPE, check=True).stdout
    subprocess.run(["tar", "-x", "-C", mod], input=archive, check=True)
    out = str(tmp_path / "legacy.json")
    env = dict(os.environ)
    env.update(FREECAD_USER_HOME=home, AC_VANILLA_FILES=json.dumps(files), AC_VANILLA_OUT=out)
    subprocess.run([exe, os.path.join(HERE, "legacy_check.py")], env=env, timeout=900,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with open(out) as fh:
        report = json.load(fh)
    assert "_fatal" not in report, report.get("_fatal")
    assert report["_addon"].startswith(mod)
    bad = {f: e for f, e in report.items() if not f.startswith("_")
           and (e["error"] or e["broken"])}
    assert not bad
