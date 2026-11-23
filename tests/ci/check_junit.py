# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fail (exit 1) when a JUnit report is missing or holds failures / errors:
freecadcmd may return 0 even when the tests failed."""

import sys
import xml.etree.ElementTree as ET

bad = 0
for path in sys.argv[1:]:
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        print("cannot read %s: %s" % (path, exc))
        bad += 1
        continue
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    for s in suites:
        f, e, t = int(s.get("failures", 0)), int(s.get("errors", 0)), int(s.get("tests", 0))
        print("%s: %d tests, %d failures, %d errors" % (path, t, f, e))
        if f or e or t == 0:
            bad += 1
sys.exit(1 if bad else 0)
