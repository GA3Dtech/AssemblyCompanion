# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""The workbench is passive: no network, no server, no AI client in the
addon, and importing the API starts nothing (Addon Index: addons that do
not run AI-generated code stay out of its "AI agents" requirements)."""

import os
import re
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG = os.path.join(ROOT, "freecad", "assembly_companion")

FORBIDDEN = re.compile(
    r"^\s*(import|from)\s+(socket|socketserver|http|urllib|requests|aiohttp|asyncio|"
    r"websocket\w*|xmlrpc|ssl|mcp|fastmcp|anthropic|openai)\b", re.M)


def test_no_network_or_ai_module_in_the_addon():
    hits = []
    for dirpath, _dirs, files in os.walk(PKG):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8") as fh:
                    for m in FORBIDDEN.finditer(fh.read()):
                        hits.append("%s: %s" % (os.path.relpath(path, ROOT), m.group(0).strip()))
    assert hits == []


def test_importing_the_api_starts_nothing():
    """Imported in a fresh Python (FreeCAD stand-in without addDocumentObserver
    or threads): an observer, a thread or a timer at import would fail here."""
    code = """
import sys, threading, types
fc = types.ModuleType("FreeCAD"); fc.GuiUp = False
fc.ParamGet = lambda p: types.SimpleNamespace(GetString=lambda k, d="": d,
    GetBool=lambda k, d=False: d, GetInt=lambda k, d=0: d)
sys.modules["FreeCAD"] = fc
before = threading.active_count()
from freecad.assembly_companion import api, library, panel_model
assert threading.active_count() == before, "thread started at import"
print("ok")
"""
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr
