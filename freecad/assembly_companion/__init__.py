# SPDX-License-Identifier: LGPL-2.1-or-later
"""Assembly Companion - workshop-grade tools for FreeCAD's built-in Assembly:
durable assemblies, visual parts library, selection sets."""

import os

from .version import __version__  # noqa: F401  (single source: package.xml)

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(PACKAGE_DIR, "resources", "icons")


def icon(name):
    """Absolute path of an icon shipped with the workbench."""
    return os.path.join(ICON_DIR, name)
