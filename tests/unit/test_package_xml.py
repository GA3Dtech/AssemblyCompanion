# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""package.xml: valid, complete, icons present, single source of the version."""

import os
import xml.etree.ElementTree as ET

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NS = "{https://wiki.freecad.org/Package_Metadata}"


def _root():
    return ET.parse(os.path.join(ROOT, "package.xml")).getroot()


def test_required_fields():
    r = _root()
    for tag in ("name", "description", "version", "date", "maintainer", "license", "url",
                "icon", "content"):
        assert r.find(NS + tag) is not None, tag
    wb = r.find(NS + "content").find(NS + "workbench")
    assert wb.find(NS + "classname").text == "AssemblyCompanionWorkbench"


def test_icons_exist():
    for el in _root().iter(NS + "icon"):
        assert os.path.isfile(os.path.join(ROOT, el.text)), el.text


def test_version_read_by_the_code():
    from freecad.assembly_companion import version, __version__
    assert __version__ == version.read_version() == _root().find(NS + "version").text


def test_every_command_icon_exists():
    import re
    text = open(os.path.join(ROOT, "freecad", "assembly_companion", "commands.py"),
                encoding="utf-8").read()
    icons = set(re.findall(r'"(\w+\.svg)"', text))
    assert icons
    for name in icons:
        assert os.path.isfile(os.path.join(ROOT, "freecad", "assembly_companion", "resources",
                                           "icons", name)), name
