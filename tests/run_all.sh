#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Run every test level locally with a FreeCAD AppImage.
#   FREECAD_APPIMAGE=/path/FreeCAD.AppImage tests/run_all.sh [unit|freecad|vanilla|gui|all]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
APPIMAGE="${FREECAD_APPIMAGE:-$HOME/Appimages/FreeCAD_26.3rc1-Linux-x86_64.AppImage}"
LEVEL="${1:-all}"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/ac_tests"
mkdir -p "$CACHE"
status=0

fc() {  # fc <user home> <command...>: run the AppImage with an isolated user home
    local home="$1"; shift
    FREECAD_USER_HOME="$home" "$APPIMAGE" "$@"
}

pytest_dir() {  # folder holding pytest for the Python of the AppImage
    local pyver
    pyver=$("$APPIMAGE" freecadcmd -c 'import sys;print("PYVER%d.%d" % sys.version_info[:2])' 2>/dev/null \
            | grep -o 'PYVER[0-9.]*' | head -1 | sed 's/PYVER//')
    local dir="$CACHE/pytest-py${pyver/./}"
    if [ ! -d "$dir/pytest" ]; then
        uv pip install -q --target "$dir" --python-version "$pyver" pytest \
          || python3 -m pip install -q --target "$dir" pytest
    fi
    echo "$dir"
}

run_unit() {
    echo "== unit"
    if python3 -c "import pytest" 2>/dev/null; then
        (cd "$ROOT" && python3 -m pytest -q tests/unit) || status=1
    else
        (cd "$ROOT" && uvx --with pytest pytest -q tests/unit) || status=1
    fi
}

run_freecad_level() {  # run_freecad_level <pytest args> <with addon: 1|0>
    local home; home=$(mktemp -d)
    if [ "$2" = "1" ]; then
        mkdir -p "$home/Mod"
        ln -s "$ROOT" "$home/Mod/AssemblyCompanion"
    fi
    AC_PYTEST_PATH="$(pytest_dir)" AC_PYTEST_ARGS="$1" AC_JUNIT="$CACHE/junit-$(echo "$1" | tr ' /' '__').xml" \
        fc "$home" freecadcmd "$HERE/run_in_freecad.py" || status=1
    rm -rf "$home"
}

case "$LEVEL" in
    unit) run_unit ;;
    freecad) run_freecad_level "tests/freecad -q" 1 ;;
    vanilla) run_freecad_level "tests/vanilla -q" 1 ;;
    all) run_unit; run_freecad_level "tests/freecad tests/vanilla -q" 1 ;;
    *) echo "usage: $0 [unit|freecad|vanilla|all]"; exit 2 ;;
esac
exit $status
