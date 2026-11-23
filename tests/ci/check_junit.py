# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fail (exit 1) when a JUnit report is missing or holds failures / errors:
freecadcmd may return 0 even when the tests failed.

    check_junit.py <report.xml> [<run.log>]

On GitHub Actions every failure is also printed as an "::error::"
annotation (test name and the start of its message), and when the report is
missing the end of the run log is: annotations can be read without signing
in, the logs cannot."""

import os
import sys
import xml.etree.ElementTree as ET

GITHUB = bool(os.environ.get("GITHUB_ACTIONS"))


def annotate(title, text, limit=3000):
    if not GITHUB:
        return
    text = text[-limit:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print("::error title=%s::%s" % (title.replace(":", " ").replace(",", " "), text))


def log_tail(path, lines=40):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:])
    except OSError as exc:
        return "no log (%s)" % exc


def main(argv):
    report = argv[0]
    log = argv[1] if len(argv) > 1 else None
    try:
        root = ET.parse(report).getroot()
    except Exception as exc:
        print("cannot read %s: %s" % (report, exc))
        annotate("No test report (%s)" % os.path.basename(report),
                 log_tail(log) if log else str(exc))
        return 1
    bad = 0
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    for s in suites:
        f, e, t = int(s.get("failures", 0)), int(s.get("errors", 0)), int(s.get("tests", 0))
        print("%s: %d tests, %d failures, %d errors" % (report, t, f, e))
        if t == 0:
            annotate("No test ran (%s)" % os.path.basename(report),
                     log_tail(log) if log else "empty report")
        if f or e or t == 0:
            bad += 1
        for case in s.iter("testcase"):
            for kind in ("failure", "error"):
                el = case.find(kind)
                if el is not None:
                    name = "%s::%s" % (case.get("classname", ""), case.get("name", ""))
                    annotate("%s %s" % (kind, name),
                             (el.get("message") or "") + "\n" + (el.text or ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
