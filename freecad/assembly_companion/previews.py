# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - previews of library files (FreeCAD, 3MF, STL, PDF)
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
previews.py (Assembly Companion) - small preview images of the files of the
parts library, made in the explorer's worker threads (no FreeCAD document
is opened):
  * .FCStd: the thumbnail FreeCAD stores in the file;
  * .3mf: the thumbnail slicers store in the package, else the mesh drawn;
  * .stl: the mesh drawn (shaded, isometric, at most MAX_TRIANGLES sampled
    triangles so that big files stay fast);
  * .pdf: the first page through the poppler tool pdftoppm when installed.
The file readers are plain Python (tested without Qt); drawing uses QImage
and QPainter, which work outside the GUI thread.
"""

import math
import os
import re
import shutil
import struct
import subprocess
import zipfile

KINDS = {".fcstd": "freecad", ".step": "step", ".stp": "step", ".stl": "mesh", ".3mf": "mesh",
         ".pdf": "pdf"}
MAX_TRIANGLES = 15000
MAX_ASCII_BYTES = 40 * 1024 * 1024       # bigger ASCII STL files are not drawn


def kind(path):
    return KINDS.get(os.path.splitext(path)[1].lower(), "")


# ----------------------------------------------------------------------
#  Readers (no Qt)
# ----------------------------------------------------------------------
def fcstd_thumbnail(path):
    """PNG bytes of the thumbnail embedded in a .FCStd (ZIP), or None."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            for cand in ("thumbnails/Thumbnail.png", "Thumbnail.png"):
                if cand in names:
                    return z.read(cand)
    except Exception:
        pass
    return None


def png_size(data):
    """(width, height) of PNG bytes, (0, 0) when not a PNG."""
    if not data or data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        return 0, 0
    return struct.unpack(">II", data[16:24])


def threemf_thumbnail(path):
    """PNG / JPEG bytes of the thumbnail of a 3MF package, or None."""
    try:
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                low = n.lower()
                if low.startswith("metadata/") and low.endswith((".png", ".jpg", ".jpeg")) \
                        and "thumbnail" in low:
                    return z.read(n)
    except Exception:
        pass
    return None


def _sampled(n, limit):
    step = max(1, int(math.ceil(n / float(limit))))
    return range(0, n, step)


def read_stl(path, limit=MAX_TRIANGLES):
    """Triangles ((x,y,z), (x,y,z), (x,y,z)) of an STL file (binary or
    ASCII), at most `limit` of them, evenly sampled."""
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(84)
        if len(head) == 84:
            count = struct.unpack("<I", head[80:84])[0]
            if 84 + 50 * count == size and count:         # binary
                tris = []
                for i in _sampled(count, limit):
                    fh.seek(84 + 50 * i + 12)
                    v = struct.unpack("<9f", fh.read(36))
                    tris.append((v[0:3], v[3:6], v[6:9]))
                return tris
    if size > MAX_ASCII_BYTES:
        return []
    with open(path, "r", errors="replace") as fh:
        text = fh.read()
    nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
    verts = []
    for x, y, z in nums:
        try:
            verts.append((float(x), float(y), float(z)))
        except ValueError:
            return []
    n = len(verts) // 3
    return [(verts[3 * i], verts[3 * i + 1], verts[3 * i + 2]) for i in _sampled(n, limit)]


def read_3mf(path, limit=MAX_TRIANGLES):
    """Triangles of the meshes of a 3MF package (build transforms ignored)."""
    import xml.etree.ElementTree as ET
    tris = []
    try:
        with zipfile.ZipFile(path) as z:
            models = [n for n in z.namelist() if n.lower().endswith(".model")]
            for name in models:
                root = ET.fromstring(z.read(name))
                for mesh in root.iter():
                    if not mesh.tag.endswith("}mesh") and mesh.tag != "mesh":
                        continue
                    verts, faces = [], []
                    for el in mesh.iter():
                        tag = el.tag.rsplit("}", 1)[-1]
                        if tag == "vertex":
                            verts.append((float(el.get("x")), float(el.get("y")),
                                          float(el.get("z"))))
                        elif tag == "triangle":
                            faces.append((int(el.get("v1")), int(el.get("v2")),
                                          int(el.get("v3"))))
                    tris += [(verts[a], verts[b], verts[c]) for a, b, c in faces]
    except Exception:
        return []
    return [tris[i] for i in _sampled(len(tris), limit)] if tris else []


# ----------------------------------------------------------------------
#  Drawing (QImage, works in worker threads)
# ----------------------------------------------------------------------
def _qt():
    try:
        from PySide import QtCore, QtGui
    except ImportError:
        from PySide6 import QtCore, QtGui
    return QtCore, QtGui


def render_mesh(tris, size=144):
    """Shaded isometric view of triangles in a QImage, or None."""
    if not tris:
        return None
    QtCore, QtGui = _qt()
    # isometric camera: rotate 45 deg around Z, then ~35.26 deg around X
    cz, sz = math.cos(math.radians(45)), math.sin(math.radians(45))
    ax = math.radians(54.7356)
    cx, sx = math.cos(ax), math.sin(ax)
    light = (0.3, -0.4, 0.86)

    def proj(p):
        x, y, z = p
        x1, y1 = x * cz - y * sz, x * sz + y * cz
        y2, z2 = y1 * cx - z * sx, y1 * sx + z * cx
        return x1, -z2, y2          # screen x, screen y (down), depth

    faces = []
    xs, ys = [], []
    for a, b, c in tris:
        pa, pb, pc = proj(a), proj(b), proj(c)
        ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        shade = abs(nx * light[0] - ny * light[1] + nz * light[2]) / ln
        faces.append(((pa[2] + pb[2] + pc[2]) / 3.0, shade, pa, pb, pc))
        xs += [pa[0], pb[0], pc[0]]
        ys += [pa[1], pb[1], pc[1]]
    w, h = (max(xs) - min(xs)) or 1.0, (max(ys) - min(ys)) or 1.0
    scale = (size - 12) / max(w, h)
    ox = (size - w * scale) / 2.0 - min(xs) * scale
    oy = (size - h * scale) / 2.0 - min(ys) * scale
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setPen(QtCore.Qt.NoPen)
    faces.sort(key=lambda f: f[0])
    for _d, shade, pa, pb, pc in faces:
        g = int(70 + 160 * shade)
        p.setBrush(QtGui.QColor(int(g * 0.55), int(g * 0.75), g))
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(pa[0] * scale + ox, pa[1] * scale + oy),
                                       QtCore.QPointF(pb[0] * scale + ox, pb[1] * scale + oy),
                                       QtCore.QPointF(pc[0] * scale + ox, pc[1] * scale + oy)]))
    p.end()
    return img


def pdf_first_page(path, size=144):
    """First page of a PDF as PNG bytes through pdftoppm, or None when the
    tool is not installed (poppler; often present on Linux)."""
    exe = shutil.which("pdftoppm")
    if not exe:
        return None
    try:
        from . import docs
        r = subprocess.run([exe, "-png", "-f", "1", "-l", "1", "-singlefile",
                            "-scale-to", str(size), path],          # PNG on stdout
                           capture_output=True, timeout=20, env=docs.clean_environment())
        return r.stdout if r.returncode == 0 and r.stdout else None
    except Exception:
        return None


def preview_image(path, size=144):
    """QImage preview of a library file, or None (STEP files, files without
    thumbnail, PDF without pdftoppm...)."""
    _QtCore, QtGui = _qt()
    k, ext = kind(path), os.path.splitext(path)[1].lower()
    data = None
    if k == "freecad":
        data = fcstd_thumbnail(path)
    elif ext == ".3mf":
        data = threemf_thumbnail(path)
        if not data:
            return render_mesh(read_3mf(path), size)
    elif ext == ".stl":
        return render_mesh(read_stl(path), size)
    elif k == "pdf":
        data = pdf_first_page(path, size)
    if not data:
        return None
    img = QtGui.QImage()
    return img if img.loadFromData(data) and not img.isNull() else None
