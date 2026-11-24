# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - package
# Copyright (C) 2026 GA3Dtech
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or (at
# your option) any later version.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <https://www.gnu.org/licenses/>.
"""Assembly Companion - workshop-grade tools for FreeCAD's built-in Assembly:
durable assemblies, visual parts library, selection sets."""

import os

from .version import __version__  # noqa: F401  (single source: package.xml)

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(PACKAGE_DIR, "resources", "icons")


def icon(name):
    """Absolute path of an icon shipped with the workbench."""
    return os.path.join(ICON_DIR, name)
