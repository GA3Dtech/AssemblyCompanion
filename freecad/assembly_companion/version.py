# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
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
