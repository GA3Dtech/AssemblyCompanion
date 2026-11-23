# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""The file manager is started without the FreeCAD bundle's variables (an
AppImage's PYTHONHOME made Nemo fail, folders no longer opened)."""

import pytest

from freecad.assembly_companion import docs

pytestmark = pytest.mark.unit


def test_clean_environment_drops_bundle_variables():
    env = {"PYTHONHOME": "/tmp/.mount_x/usr", "QT_QPA_PLATFORM": "xcb", "APPIMAGE": "/a",
           "HOME": "/home/u", "DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "X-Cinnamon"}
    clean = docs.clean_environment(env)
    assert clean == {"HOME": "/home/u", "DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "X-Cinnamon"}
    assert env["PYTHONHOME"]                      # the original is not modified


def test_open_in_file_manager_uses_clean_environment(monkeypatch):
    seen = {}

    class FakePopen(object):
        def __init__(self, cmd, env=None, **kw):
            seen["cmd"], seen["env"] = cmd, env

    monkeypatch.setattr(docs.sys, "platform", "linux")
    monkeypatch.setattr(docs.subprocess, "Popen", FakePopen)
    monkeypatch.setenv("PYTHONHOME", "/tmp/.mount_x/usr")
    assert docs.open_in_file_manager("/some/folder")
    assert seen["cmd"] == ["xdg-open", "/some/folder"] and "PYTHONHOME" not in seen["env"]
