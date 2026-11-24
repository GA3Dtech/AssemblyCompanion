# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Every source file carries the SPDX licence line; the modules of the
addon also the coding line and the LGPL header (repository rules and Addon
Index requirements)."""

import os

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPDX = "SPDX-License-Identifier: LGPL-2.1-or-later"


def _files(ext, top=""):
    for dirpath, dirs, files in os.walk(os.path.join(ROOT, top)):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "legacy", ".claude")]
        for f in files:
            if f.endswith(ext):
                yield os.path.join(dirpath, f)


def test_spdx_everywhere():
    missing = []
    for ext in (".py", ".qml", ".sh", ".yml", ".yaml", ".toml"):
        for path in _files(ext):
            with open(path, encoding="utf-8") as fh:
                head = "".join(fh.readlines()[:5])
            if SPDX not in head:
                missing.append(os.path.relpath(path, ROOT))
    assert missing == []


def test_addon_modules_have_the_full_header():
    bad = []
    for path in _files(".py", os.path.join("freecad", "assembly_companion")):
        with open(path, encoding="utf-8") as fh:
            text = fh.read(2000)
        if not text.startswith("# -*- coding: utf-8 -*-\n# " + SPDX) or \
                "GNU Lesser General Public License" not in text:
            bad.append(os.path.relpath(path, ROOT))
    assert bad == []
