# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Toolbar and menu follow the workflow: parts library first, finishing
tools (fasteners, alignment, reactivation) last; every command once."""

import ast
import os

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "freecad", "assembly_companion", "commands.py")


def _groups():
    """GROUPS read from the source (commands.py imports FreeCADGui)."""
    with open(SRC, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "GROUPS":
            return ast.literal_eval(node.value)
    raise AssertionError("GROUPS not found")


def _registered():
    with open(SRC, encoding="utf-8") as fh:
        text = fh.read()
    import re
    return set(re.findall(r'^    "(AssemblyCompanion_\w+)": _Command\(', text, re.M))


def test_order_of_the_workflow():
    flat = [c for _name, cmds in _groups() for c in cmds]
    assert flat[0] == "AssemblyCompanion_Explorer"
    assert flat[-3:] == ["AssemblyCompanion_Fasteners", "AssemblyCompanion_Align",
                         "AssemblyCompanion_Reactivate"]


def test_every_command_once():
    flat = [c for _name, cmds in _groups() for c in cmds]
    assert len(flat) == len(set(flat))
    assert set(flat) | {"AssemblyCompanion_Repair"} == _registered()
