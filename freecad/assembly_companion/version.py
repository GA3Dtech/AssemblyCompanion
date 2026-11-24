# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - version from package.xml
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
"""
version.py (Assembly Companion) - the version of the workbench, read from
package.xml, the only place it is written (the Addon Manager reads it there).
"""

import os
import xml.etree.ElementTree as ET

PACKAGE_XML = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "package.xml")


def read_version(path=PACKAGE_XML):
    """<version> of package.xml, "unknown" when it cannot be read."""
    try:
        root = ET.parse(path).getroot()
        for el in root.iter():
            if el.tag.rsplit("}", 1)[-1] == "version" and el.text:
                return el.text.strip()
    except Exception:
        pass
    return "unknown"


__version__ = read_version()
