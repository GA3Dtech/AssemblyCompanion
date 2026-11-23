# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Unit tests run with a plain Python. When FreeCAD is not importable, minimal
stand-ins of the FreeCAD and Part modules are installed: only what the
modules touch at import time and what the pure functions under test call
(parameters, console). Inside freecadcmd the real modules are used.
"""

import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _ParamGroup(object):
    def __init__(self):
        self.values = {}

    def _get(self, key, default):
        return self.values.get(key, default)

    GetBool = GetInt = GetFloat = GetString = _get

    def _set(self, key, value):
        self.values[key] = value

    SetBool = SetInt = SetFloat = SetString = _set


class _Console(object):
    def __init__(self):
        self.messages = []

    def _print(self, msg):
        self.messages.append(msg)

    PrintMessage = PrintWarning = PrintError = PrintLog = _print


def _install_stubs():
    try:
        import FreeCAD  # noqa: F401
        return False
    except ImportError:
        pass
    groups = {}
    fc = types.ModuleType("FreeCAD")
    fc.GuiUp = False
    fc.Console = _Console()
    fc.ParamGet = lambda path: groups.setdefault(path, _ParamGroup())
    fc.Version = lambda: ["1", "0", "0", "stub"]
    fc.listDocuments = lambda: {}
    fc.ActiveDocument = None
    fc.Vector = lambda *a: a
    sys.modules["FreeCAD"] = fc
    sys.modules["Part"] = types.ModuleType("Part")
    return True


STUBBED = _install_stubs()


@pytest.fixture
def language(monkeypatch):
    """Force the session language of i18n (and reset its table)."""
    from freecad.assembly_companion import i18n

    def _set(code):
        monkeypatch.setattr(i18n, "_code", code)
        monkeypatch.setattr(i18n, "_table", None)
    yield _set
    i18n._code = None
    i18n._table = None
