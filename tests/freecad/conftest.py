# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Integration tests, run INSIDE FreeCAD (tests/run_in_freecad.py): fixtures
are built once per session in a temporary folder (build_fixtures), each
test works on a fresh copy of a project and every document is closed after
the test.
"""

import os
import shutil
import sys

import pytest

try:
    import FreeCAD as App
except ImportError:                       # plain Python: nothing to run here
    App = None

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TESTS, "fixtures"))


def pytest_collection_modifyitems(config, items):
    if App is None:
        skip = pytest.mark.skip(reason="needs FreeCAD (run tests/run_in_freecad.py)")
        for it in items:
            if "freecad" in it.nodeid:
                it.add_marker(skip)


@pytest.fixture(scope="session")
def fixtures_root(tmp_path_factory):
    import build_fixtures
    root = str(tmp_path_factory.mktemp("fixtures"))
    build_fixtures.build_all(root, states=False)
    close_all()
    return root


@pytest.fixture
def project(fixtures_root, tmp_path):
    """project("basic") -> path of a fresh copy of that project folder."""
    def _copy(name):
        dst = str(tmp_path / name)
        shutil.copytree(os.path.join(fixtures_root, name), dst)
        return dst
    return _copy


def close_all():
    for name in list(App.listDocuments()):
        try:
            App.closeDocument(name)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _close_documents():
    yield
    if App is not None:
        close_all()


def open_doc(path):
    d = App.openDocument(path)
    d.recompute()
    return d


def reopen(doc):
    """Save, close every document, reopen `doc`'s file."""
    path = doc.FileName
    doc.save()
    close_all()
    return open_doc(path)


def placements(doc):
    return {o.Name: o.Placement for o in doc.Objects if o.isDerivedFrom("App::Link")}


def same_placements(a, b, tol=1e-6):
    return all(k in b and a[k].isSame(b[k], tol) for k in a)
