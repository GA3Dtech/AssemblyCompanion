#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# CI helper: download (cached), extract and prepare a FreeCAD AppImage.
#   tests/ci/freecad_setup.sh <release tag> <cache dir>
#   tests/ci/freecad_setup.sh --resolve weekly   # prints the latest weekly tag
# Writes to $GITHUB_ENV: FC_APPRUN (AppRun path), AC_FREECADCMD (wrapper),
# AC_PYTEST_PATH (pytest for the embedded Python).
set -euo pipefail
AUTH=()
if [ -n "${GITHUB_TOKEN:-}" ]; then AUTH=(-H "Authorization: Bearer $GITHUB_TOKEN"); fi
if [ "$1" = "--resolve" ]; then
    # weekly: latest development build; a series such as 26.3: its stable
    # release when published, else its newest release candidate; anything
    # else: that exact tag
    curl -fsSL "${AUTH[@]}" "https://api.github.com/repos/FreeCAD/FreeCAD/releases?per_page=60" \
        | python3 -c "
import json, re, sys
want = sys.argv[1]
tags = [(r['tag_name'], r['prerelease']) for r in json.load(sys.stdin)]
if want == 'weekly':
    print([t for t, _p in tags if t.startswith('weekly-')][0])
elif re.fullmatch(r'\d+\.\d+', want):
    serie = [(t, p) for t, p in tags if re.match(re.escape(want) + r'(\.\d+|rc\d+)?$', t)]
    stable = [t for t, p in serie if not p]
    print(stable[0] if stable else serie[0][0])
else:
    print(want)
" "$2"
    exit 0
fi
TAG="$1"
CACHE="$2"
mkdir -p "$CACHE"
APPIMAGE="$CACHE/FreeCAD-$TAG.AppImage"
if [ ! -s "$APPIMAGE" ]; then
    # Exact asset of the pinned release, resolved through the GitHub API
    URL=$(curl -fsSL "${AUTH[@]}" \
          "https://api.github.com/repos/FreeCAD/FreeCAD/releases/tags/$TAG" \
          | python3 -c "import json,sys; r=json.load(sys.stdin); print([a['browser_download_url'] for a in r['assets'] if a['name'].endswith('.AppImage') and 'x86_64' in a['name']][0])")
    echo "Downloading $URL"
    curl -fsSL -o "$APPIMAGE" "$URL"
fi
chmod +x "$APPIMAGE"
# No FUSE on the runners: extract instead of mounting
rm -rf "$CACHE/squashfs-root"
(cd "$CACHE" && "$APPIMAGE" --appimage-extract >/dev/null)
APPRUN="$CACHE/squashfs-root/AppRun"
WRAP="$CACHE/freecadcmd"
printf '#!/usr/bin/env bash\nexec "%s" freecadcmd "$@"\n' "$APPRUN" > "$WRAP"
chmod +x "$WRAP"
PYVER=$("$APPRUN" freecadcmd -c 'import sys;print("PYVER%d.%d" % sys.version_info[:2])' 2>/dev/null \
        | grep -o 'PYVER[0-9.]*' | head -1 | sed 's/PYVER//')
echo "FreeCAD $TAG embeds Python $PYVER"
PYT="$CACHE/pytest-py${PYVER/./}"
python3 -m pip install -q --target "$PYT" --python-version "$PYVER" --only-binary=:all: pytest
{
    echo "FC_APPRUN=$APPRUN"
    echo "AC_FREECADCMD=$WRAP"
    echo "AC_PYTEST_PATH=$PYT"
} >> "${GITHUB_ENV:-/dev/null}"
