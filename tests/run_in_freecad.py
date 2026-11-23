# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
tests/run_in_freecad.py (Assembly Companion) - run pytest INSIDE FreeCAD.

    AC_PYTEST_ARGS="tests/freecad -q" AC_PYTEST_PATH=<dir with pytest> \\
        freecadcmd /abs/path/tests/run_in_freecad.py

* AC_PYTEST_PATH: folder holding pytest for FreeCAD's own Python
  (pip install --target ...), added to sys.path;
* AC_PYTEST_ARGS: pytest arguments (default: tests/freecad);
* AC_JUNIT: optional JUnit XML report path.
Ends with os._exit(code): freecadcmd may return 0 even when a script fails.
"""

import os
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

code = 3
try:
    extra = os.environ.get("AC_PYTEST_PATH")
    if extra and extra not in sys.path:
        sys.path.insert(0, extra)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import pytest
    args = shlex.split(os.environ.get("AC_PYTEST_ARGS", "tests/freecad"))
    if os.environ.get("AC_JUNIT"):
        args.append("--junitxml=" + os.environ["AC_JUNIT"])
    args += ["-p", "no:cacheprovider"]
    code = int(pytest.main(args))
except SystemExit as exc:
    code = int(exc.code or 0)
except Exception:
    import traceback
    traceback.print_exc()
    code = 4
sys.stdout.flush()
sys.stderr.flush()
os._exit(code)
