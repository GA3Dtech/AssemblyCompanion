# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - local explorer and visual component insertion
# Derived from "PiStock Local Explorer"
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
explorer.py (Assembly Companion) - browse a local "master" folder of FreeCAD files with
thumbnails, open them, or INSERT them visually into the active assembly /
Std_Part container (the source file does not need to be open).

Layout (from PiStock Local Explorer): one block per folder, indented by
depth, each with a horizontal strip of mini thumbnails.

Speed-ups over the original macro (3600 files on a network share):
  * folder scan with os.scandir: on Windows the file size / date come with
    the directory listing, no extra network round trip per file;
  * the scan result is cached on the local disk: the view is shown at once
    from the cache, then refreshed by a background rescan;
  * thumbnails are cached on the local disk (scaled PNG, keyed by path +
    date + size): a file is unzipped only once, until it changes;
  * missing thumbnails are extracted by a pool of worker threads, results are
    pushed to the GUI by a timer (no blocking, no processEvents loop);
  * a single style sheet for all cards instead of one per card.

User-facing texts are in English, translated through i18n.tr().
"""

import os
import json
import queue
import hashlib
import zipfile
import concurrent.futures

import FreeCAD as App

try:
    from PySide import QtWidgets, QtCore, QtGui
except ImportError:                       # outside FreeCAD (tests)
    from PySide6 import QtWidgets, QtCore, QtGui

from . import docs
from . import prefs
from .i18n import tr

VERSION = "1.0"

# ----------------------------------------------------------------------
#  Dimensions (same as PiStock Local Explorer)
# ----------------------------------------------------------------------
THUMB = 72              # thumbnail side on screen
THUMB_CACHE = 144       # thumbnail side stored in cache (sharp on HiDPI)
CARD_W = 88
CARD_H = 104
INDENT_PX = 22          # horizontal offset per tree level
STRIP_H = CARD_H + 26   # strip height (card + scroll bar)
WORKERS = 16            # parallel thumbnail extractions (I/O bound)
BATCH_PER_TICK = 60     # thumbnails applied to the GUI per timer tick

PISTOCK_PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/PiStock"
PARAM_DIR_KEY = "LocalMasterDir"
PARAM_FREEZE_KEY = "FreezeOnInsert"

STYLE = """
QFrame#card { background: white; border: 1px solid #d2d2d7; border-radius: 6px; }
QFrame#card:hover { border-color: #059669; background: #ecfdf5; }
QLabel#thumb { background: #f5f5f7; border-radius: 4px; color: #c7c7cc; }
QLabel#name { font-size: 10px; }
QLabel#rel { color: #9ca3af; font-size: 11px; }
QLabel#count { color: #6b7280; font-size: 11px; background: #ecfdf5;
               padding: 1px 7px; border-radius: 8px; }
QPushButton#folder { font-weight: 600; font-size: 13px; color: #065f46; border: none;
                     background: transparent; text-align: left; padding: 0 2px; }
QPushButton#folder:hover { text-decoration: underline; }
QScrollArea { border: none; }
"""


# ----------------------------------------------------------------------
#  Parameters and cache location
# ----------------------------------------------------------------------
def get_saved_dir():
    try:
        d = prefs.get(PARAM_DIR_KEY)
        if not d:   # reuse the PiStock setting the first time
            d = App.ParamGet(PISTOCK_PARAM_PATH).GetString(PARAM_DIR_KEY, "")
        return d
    except Exception:
        return ""


def set_saved_dir(path):
    try:
        prefs.put(PARAM_DIR_KEY, path or "")
    except Exception:
        pass


def get_freeze_on_insert():
    try:
        return prefs.get(PARAM_FREEZE_KEY)
    except Exception:
        return False


def set_freeze_on_insert(value):
    try:
        prefs.put(PARAM_FREEZE_KEY, bool(value))
    except Exception:
        pass


def cache_dir():
    base = None
    for fn in ("getUserCachePath", "getUserAppDataDir"):
        try:
            base = getattr(App, fn)()
            if base:
                break
        except Exception:
            pass
    d = os.path.join(base or os.path.expanduser("~"), "assembly_explorer_cache")
    os.makedirs(os.path.join(d, "thumbs"), exist_ok=True)
    return d


def _key(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
#  Folder scan (pure Python, runs in a worker thread)
# ----------------------------------------------------------------------
def scan_master(master):
    """Return {folder: [(path, mtime, size), ...]} for every folder holding
    .FCStd files directly. os.scandir gives size/date without an extra
    request per file on Windows (they come with the listing)."""
    result = {}

    def walk(d):
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            return
        files, subdirs = [], []
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if not e.name.startswith('.'):
                        subdirs.append(e.path)
                elif e.name.lower().endswith(".fcstd"):
                    st = e.stat()
                    files.append((e.path, st.st_mtime, st.st_size))
            except OSError:
                pass
        if files:
            files.sort(key=lambda f: os.path.basename(f[0]).lower())
            result[d] = files
        for s in sorted(subdirs, key=str.lower):
            walk(s)

    walk(master)
    return result


def _scan_cache_file(master):
    return os.path.join(cache_dir(), "scan_%s.json" % _key(os.path.normcase(master)))


def load_scan_cache(master):
    try:
        with open(_scan_cache_file(master), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {d: [tuple(f) for f in files] for d, files in data.items()}
    except Exception:
        return None


def save_scan_cache(master, scan):
    try:
        with open(_scan_cache_file(master), "w", encoding="utf-8") as fh:
            json.dump(scan, fh)
    except Exception:
        pass


# ----------------------------------------------------------------------
#  Thumbnails (worker threads; QImage is thread-safe, QPixmap is not)
# ----------------------------------------------------------------------
def extract_fcstd_thumbnail(path):
    """PNG bytes of the thumbnail embedded in a .FCStd (ZIP archive), or None."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            for cand in ("thumbnails/Thumbnail.png", "Thumbnail.png"):
                if cand in names:
                    return z.read(cand)
    except Exception:
        pass
    return None


def load_thumbnail(cdir, path, mtime, size):
    """Return a small QImage for the file, or None. Uses the local disk cache;
    the .FCStd is unzipped only when it changed since last time. Files without
    thumbnail get a '.none' marker so they are not unzipped again."""
    k = _key(os.path.normcase(path), mtime, size)
    png = os.path.join(cdir, "thumbs", k + ".png")
    none = os.path.join(cdir, "thumbs", k + ".none")
    if os.path.exists(png):
        img = QtGui.QImage(png)
        return None if img.isNull() else img
    if os.path.exists(none):
        return None
    data = extract_fcstd_thumbnail(path)
    img = QtGui.QImage()
    if not data or not img.loadFromData(data) or img.isNull():
        try:
            open(none, "w").close()
        except OSError:
            pass
        return None
    img = img.scaled(THUMB_CACHE, THUMB_CACHE, QtCore.Qt.KeepAspectRatio,
                     QtCore.Qt.SmoothTransformation)
    try:
        img.save(png, "PNG")
    except Exception:
        pass
    return img


# ----------------------------------------------------------------------
#  Insertion into the active assembly / Std_Part
# ----------------------------------------------------------------------
def _same_file(a, b):
    return docs.same_file(a, b)


def _source_document(path, keep=None):
    """Already opened document for `path`, or open it HIDDEN (no tab),
    keeping `keep` as the active document (see docs.py)."""
    return docs.open_source(path, keep)


def _kind(o):
    """'part', 'body', 'solid', 'group' (container to walk into, not
    insertable itself) or None. Body is tested before Part::Feature because
    PartDesign::Body derives from it."""
    try:
        if o.isDerivedFrom("App::Part"):
            return "part"
        if o.isDerivedFrom("PartDesign::Body"):
            return "body"
        if o.isDerivedFrom("App::DocumentObjectGroup"):
            return "group"
        if o.isDerivedFrom("Part::Feature") and not o.Shape.isNull() \
                and o.Shape.Solids:
            return "solid"
    except Exception:
        pass
    return None


def _top_level_children(container):
    """Children of an App::Part / group that are not consumed by a sibling
    (e.g. the Box and Cylinder of a Cut): the container-level equivalent of
    Document.RootObjects."""
    group = list(getattr(container, "Group", []) or [])
    members = set(c.Name for c in group)
    return [c for c in group
            if not any(p.Name in members for p in c.InList if p is not container)]


def _candidates(doc):
    """Objects of the source file that can be inserted, as (object, depth)
    pairs in tree order. Root App::Part first (e.g. the Part made by PiStock
    'wrap bodies'), then Bodies, then other solids; the content of App::Part
    containers and groups is listed right after them, so Bodies nested in a
    Part can be inserted on their own. Links to objects of the same file are
    followed (their target is no longer a root object). Bodies are not walked
    into (their features are not insertable components)."""
    order = {"part": 0, "group": 0, "body": 1, "solid": 2}
    result, seen = [], set()

    def resolve(o):
        # An App::Link to an object of the same file hides its target from
        # RootObjects (e.g. a mirrored copy of a Part): list the target instead
        if o.isDerivedFrom("App::Link"):
            try:
                t = o.getLinkedObject(True)
            except Exception:
                t = None
            return t if t is not None and t is not o and t.Document is doc else None
        return o

    def walk(objs, depth):
        objs = [t for t in (resolve(o) for o in objs) if t is not None]
        typed = [(o, _kind(o)) for o in objs]
        typed = [(o, k) for o, k in typed if k is not None]
        typed.sort(key=lambda ok: order[ok[1]])     # stable: keeps tree order
        for o, k in typed:
            # Checked here, not when filtering: walking a Part may already have
            # listed a sibling (e.g. a Body also reached through a root Link)
            if o.Name in seen:
                continue
            seen.add(o.Name)
            if k == "group":
                # Not insertable: list its content at the same depth
                walk(_top_level_children(o), depth)
                continue
            result.append((o, depth))
            if k == "part":
                walk(_top_level_children(o), depth + 1)

    walk(doc.RootObjects, 0)
    # Safety net: Parts and Bodies still unreachable from the roots (only
    # referenced by some other feature) are listed at the end
    walk([o for o in doc.Objects if _kind(o) in ("part", "body")], 0)
    return result


def _target_container(doc):
    """Active assembly / Std_Part ('assembly' or 'part' active object), or the only
    Assembly of the document, or None (document root)."""
    try:
        import FreeCADGui as Gui
        # The view of `doc` itself: the active document may be another one
        # (e.g. the new part just created)
        view = Gui.getDocument(doc.Name).ActiveView
        # 26.x records the active assembly under "assembly", 1.0 under "part"
        for key in ("assembly", "part"):
            act = view.getActiveObject(key)
            if act is not None and act.Document is doc:
                return act
    except Exception:
        pass
    asm = [o for o in doc.Objects if o.isDerivedFrom("Assembly::AssemblyObject")]
    return asm[0] if len(asm) == 1 else None


def choose_object(src_doc, parent_widget, title, name, preferred=None):
    """Object of `src_doc` to use as a component: the only candidate, or the
    one picked in a list showing the tree. `preferred` (internal name) is
    selected by default. None when cancelled; RuntimeError when the file
    holds no candidate."""
    cands = _candidates(src_doc)
    if not cands:
        raise RuntimeError(tr("“{name}” contains no Part, Body or solid.").format(name=name))
    if len(cands) == 1:
        return cands[0][0]
    # Indent nested objects to show the tree; add the internal name when
    # two objects share a label, so every entry is unique
    dup = set(o.Label for o, _ in cands
              if sum(1 for c, _ in cands if c.Label == o.Label) > 1)
    labels = ["%s%s%s  (%s)" % ("      " * d, o.Label,
                                " [%s]" % o.Name if o.Label in dup else "",
                                o.TypeId.split("::")[-1])
              for o, d in cands]
    current = next((i for i, (o, _d) in enumerate(cands) if o.Name == preferred), 0)
    choix, ok = QtWidgets.QInputDialog.getItem(
        parent_widget, title,
        tr("“{name}” contains several objects:").format(name=name), labels, current, False)
    if not ok:
        return None
    return cands[labels.index(choix)][0]


def insert_component(path, parent_widget=None, freeze=False):
    """Insert the main object of `path` as an App::Link into the active
    assembly / Std_Part of the active document. Returns the new Link."""
    import FreeCADGui as Gui
    doc = docs.working_document()
    name = os.path.basename(path)
    if doc is None:
        raise RuntimeError(tr("No active document: open or create the assembly first."))
    if _same_file(doc.FileName, path):
        raise RuntimeError(tr("A file cannot be inserted into itself."))
    src_doc = _source_document(path, doc)
    obj = choose_object(src_doc, parent_widget, tr("Insert component"), name)
    if obj is None:
        return None
    container = _target_container(doc)
    doc.openTransaction(tr("Insert component"))
    try:
        link = doc.addObject("App::Link", obj.Name)
        link.setLink(obj)
        link.Label = obj.Label
        if container is not None:
            container.addObject(link)
        doc.recompute()
    finally:
        doc.commitTransaction()
    App.Console.PrintMessage(
        tr("Explorer: {name} inserted into {target}").format(
            name=obj.Label, target=container.Label if container else doc.Label) + "\n")
    if freeze:
        try:
            from . import freeze
            freeze.figer(doc, [link])
        except Exception as e:
            App.Console.PrintWarning(
                tr("Explorer: freezing failed ({error})").format(error=e) + "\n")
    docs.activate(doc)          # the assembly stays the active document
    try:
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(link)
    except Exception:
        pass
    return link


# ----------------------------------------------------------------------
#  File card
# ----------------------------------------------------------------------
class FileCard(QtWidgets.QFrame):
    """Mini card of a .FCStd file: thumbnail + name. Left click = main
    action (open or insert), right click = menu with every action."""

    def __init__(self, path, mtime, size, explorer):
        super().__init__()
        self.path, self.mtime, self.size = path, mtime, size
        self.explorer = explorer
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.setObjectName("card")
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(2)
        lay.setContentsMargins(4, 4, 4, 4)
        self.thumb = QtWidgets.QLabel("…")
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(THUMB, THUMB)
        self.thumb.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.thumb, alignment=QtCore.Qt.AlignCenter)
        lbl = QtWidgets.QLabel(self.name)
        lbl.setObjectName("name")
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.setToolTip(path)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.explorer.main_action(self.path)
        elif event.button() == QtCore.Qt.RightButton:
            self.explorer.card_menu(self, event)

    def set_image(self, img):
        if img is None:
            self.thumb.setText(tr("(no\nthumbnail)"))
            return
        pix = QtGui.QPixmap.fromImage(img).scaled(
            THUMB, THUMB, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.thumb.setPixmap(pix)
        self.thumb.setText("")


# ----------------------------------------------------------------------
#  Explorer widget
# ----------------------------------------------------------------------
class ExplorerWidget(QtWidgets.QWidget):
    """mode = 'open' (left click opens the file) or 'insert' (left click
    inserts it into the active assembly). Both actions are always available
    from the right-click menu."""

    def __init__(self, mode="open", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.cdir = cache_dir()
        self.cards = {}            # path -> FileCard
        self.blocks = []           # (block widget, [cards], folder rel path)
        self.generation = 0        # invalidates results of previous loads
        self.results = queue.Queue()
        self.pool = None
        self.scan_future = None
        self.current_scan = None
        self._build_ui()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._drain)
        self.timer.start(30)
        self.filter_timer = QtCore.QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.timeout.connect(self.apply_filter)
        saved = get_saved_dir()
        if saved:
            self.path_edit.setText(saved)
            if os.path.isdir(saved):
                QtCore.QTimer.singleShot(0, self.refresh)

    # --- UI ------------------------------------------------------------
    def _build_ui(self):
        self.setStyleSheet(STYLE)      # ONE style sheet for every card
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel(tr("Master folder:")))
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.returnPressed.connect(self.refresh)
        row.addWidget(self.path_edit, 1)
        b = QtWidgets.QPushButton(tr("Browse…"))
        b.clicked.connect(self._browse)
        row.addWidget(b)
        b = QtWidgets.QPushButton(tr("Scan"))
        b.setToolTip(tr("Read the folder again (unchanged thumbnails stay cached)"))
        b.clicked.connect(self.refresh)
        row.addWidget(b)
        main.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText(tr("Filter by file or folder name…"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(lambda *_: self.filter_timer.start(200))
        row.addWidget(self.filter_edit, 1)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem(tr("Click = open"), "open")
        self.mode_combo.addItem(tr("Click = insert into the assembly"), "insert")
        self.mode_combo.setCurrentIndex(1 if self.mode == "insert" else 0)
        self.mode_combo.currentIndexChanged.connect(
            lambda *_: setattr(self, "mode", self.mode_combo.currentData()))
        row.addWidget(self.mode_combo)
        main.addLayout(row)

        self.freeze_check = QtWidgets.QCheckBox(tr("Freeze on insertion"))
        self.freeze_check.setToolTip(tr("Insert the part, then freeze it at once "
                                        "(Assembly Companion)"))
        self.freeze_check.setChecked(get_freeze_on_insert())
        self.freeze_check.toggled.connect(set_freeze_on_insert)
        main.addWidget(self.freeze_check)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: #6b7280; font-size: 12px;")
        main.addWidget(self.status)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        main.addWidget(self.scroll, 1)
        self._new_container()

    def _new_container(self):
        self.tree_container = QtWidgets.QWidget()
        self.tree_layout = QtWidgets.QVBoxLayout(self.tree_container)
        self.tree_layout.setSpacing(10)
        self.tree_layout.setAlignment(QtCore.Qt.AlignTop)
        self.scroll.setWidget(self.tree_container)    # old container is deleted

    def _browse(self):
        start = self.path_edit.text() or os.path.expanduser("~")
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, tr("Choose the master folder to explore"), start)
        if path:
            self.path_edit.setText(path)
            self.refresh()

    # --- Scan ----------------------------------------------------------
    def refresh(self):
        master = self.path_edit.text().strip()
        set_saved_dir(master)
        if not master or not os.path.isdir(master):
            self._show_message(tr("Folder not found: {path}").format(path=master) if master else
                               tr("Enter a master folder above, then click “Scan”."))
            return
        cached = load_scan_cache(master)
        if cached:
            self._build(master, cached)            # instant display from cache
            self.status.setText(self.status.text() + "   " + tr("(checking the folder…)"))
        else:
            self._show_message(tr("Scanning the folder…"))
        # Background rescan; the view is rebuilt only if something changed
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.scan_future = ex.submit(scan_master, master)
        self.scan_master = master
        ex.shutdown(wait=False)

    def _check_scan(self):
        f = self.scan_future
        if f is None or not f.done():
            return
        self.scan_future = None
        try:
            scan = f.result()
        except Exception as e:
            self.status.setText(tr("Scan error: {error}").format(error=e))
            return
        save_scan_cache(self.scan_master, scan)
        if scan != self.current_scan:
            self._build(self.scan_master, scan)
        else:
            self.status.setText(self._summary(scan))

    # --- Display -------------------------------------------------------
    def _summary(self, scan):
        total = sum(len(v) for v in scan.values())
        return tr("{files} file(s) in {folders} folder(s)").format(files=total, folders=len(scan))

    def _show_message(self, text):
        self._stop_loading()
        self._new_container()
        self.cards, self.blocks, self.current_scan = {}, [], None
        lbl = QtWidgets.QLabel(text)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setStyleSheet("color: #6b7280; padding: 40px;")
        self.tree_layout.addWidget(lbl)
        self.status.setText("")

    def _stop_loading(self):
        self.generation += 1
        if self.pool is not None:
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.pool = None

    def _build(self, master, scan):
        self._stop_loading()
        self.current_scan = scan
        if not scan:
            self._show_message(tr("No FreeCAD file (.FCStd) under this folder."))
            return
        # Folders holding files + all their parents up to master
        relevant = {master}
        for d in scan:
            cur = d
            while True:
                relevant.add(cur)
                if os.path.normcase(os.path.normpath(cur)) == \
                        os.path.normcase(os.path.normpath(master)):
                    break
                parent = os.path.dirname(cur)
                if parent == cur:
                    break
                cur = parent

        def sort_key(d):
            rel = os.path.relpath(d, master)
            return () if rel == "." else tuple(p.lower() for p in rel.split(os.sep))

        scroll_pos = self.scroll.verticalScrollBar().value()
        self._new_container()
        self.cards, self.blocks = {}, []
        self.tree_container.setUpdatesEnabled(False)
        for d in sorted(relevant, key=sort_key):
            self._add_block(master, d, len(sort_key(d)), scan.get(d, []))
        self.tree_layout.addStretch()
        self.tree_container.setUpdatesEnabled(True)
        QtCore.QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(scroll_pos))
        self.status.setText(self._summary(scan))
        self.apply_filter()

        # Thumbnails: cached ones are fast, missing ones are unzipped in parallel
        gen = self.generation
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS)
        for card in self.cards.values():
            self.pool.submit(self._job, gen, card.path, card.mtime, card.size)

    def _job(self, gen, path, mtime, size):
        if gen != self.generation:
            return
        try:
            img = load_thumbnail(self.cdir, path, mtime, size)
        except Exception:
            img = None
        self.results.put((gen, path, img))

    def _drain(self):
        """GUI timer: apply finished thumbnails, a batch at a time."""
        self._check_scan()
        for _ in range(BATCH_PER_TICK):
            try:
                gen, path, img = self.results.get_nowait()
            except queue.Empty:
                return
            if gen != self.generation:
                continue
            card = self.cards.get(path)
            if card is not None:
                card.set_image(img)

    def _add_block(self, master, path, depth, files):
        block = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(block)
        v.setSpacing(4)
        v.setContentsMargins(depth * INDENT_PX, 0, 0, 0)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        icon = QtWidgets.QLabel()
        sp = getattr(getattr(QtWidgets.QStyle, "StandardPixmap", QtWidgets.QStyle), "SP_DirIcon")
        icon.setPixmap(self.style().standardIcon(sp).pixmap(16, 16))
        header.addWidget(icon)
        rel = "" if depth == 0 else os.path.relpath(path, master)
        btn = QtWidgets.QPushButton(tr("(master)") if depth == 0 else os.path.basename(path))
        btn.setObjectName("folder")
        btn.setFlat(True)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setToolTip(tr("Open this folder in the file manager"))
        btn.clicked.connect(lambda checked=False, p=path: self.open_in_os(p))
        header.addWidget(btn)
        if rel:
            r = QtWidgets.QLabel(rel)
            r.setObjectName("rel")
            header.addWidget(r)
        header.addStretch()
        cards = []
        if files:
            c = QtWidgets.QLabel(str(len(files)))
            c.setObjectName("count")
            header.addWidget(c)
        v.addLayout(header)
        if files:
            strip = QtWidgets.QScrollArea()
            strip.setWidgetResizable(True)
            strip.setFixedHeight(STRIP_H)
            strip.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            inner = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(inner)
            h.setSpacing(8)
            h.setContentsMargins(2, 2, 2, 2)
            h.setAlignment(QtCore.Qt.AlignLeft)
            for fpath, mtime, size in files:
                card = FileCard(fpath, mtime, size, self)
                h.addWidget(card)
                self.cards[fpath] = card
                cards.append(card)
            h.addStretch()
            strip.setWidget(inner)
            v.addWidget(strip)
        self.tree_layout.addWidget(block)
        self.blocks.append((block, cards, rel.lower()))

    # --- Filter --------------------------------------------------------
    def apply_filter(self):
        txt = self.filter_edit.text().strip().lower()
        shown = 0
        self.tree_container.setUpdatesEnabled(False)
        for block, cards, rel in self.blocks:
            if not txt:
                for c in cards:
                    c.setVisible(True)
                block.setVisible(True)
                shown += len(cards)
                continue
            folder_match = txt in rel
            n = 0
            for c in cards:
                ok = folder_match or txt in c.name.lower()
                c.setVisible(ok)
                n += ok
            block.setVisible(n > 0)
            shown += n
        self.tree_container.setUpdatesEnabled(True)
        if txt and self.current_scan:
            self.status.setText(tr("{n} file(s) match “{text}”").format(n=shown, text=txt))
        elif self.current_scan:
            self.status.setText(self._summary(self.current_scan))

    # --- Actions -------------------------------------------------------
    def main_action(self, path):
        if self.mode == "insert":
            self.insert_file(path)
        else:
            self.open_file(path)

    def card_menu(self, card, event):
        menu = QtWidgets.QMenu(self)
        menu.addAction(tr("Insert into the active assembly"), lambda: self.insert_file(card.path))
        menu.addAction(tr("Open"), lambda: self.open_file(card.path))
        menu.addAction(tr("Open folder"), lambda: self.open_in_os(os.path.dirname(card.path)))
        pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") \
            else event.globalPos()
        menu.exec(pos) if hasattr(menu, "exec") else menu.exec_(pos)

    def insert_file(self, path):
        try:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            try:
                link = insert_component(path, self, self.freeze_check.isChecked())
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            if link is not None:
                self.status.setText(tr("“{name}” inserted.").format(name=link.Label))
        except Exception as e:
            App.Console.PrintError(
                tr("Explorer: insertion failed: {error}").format(error=e) + "\n")
            QtWidgets.QMessageBox.warning(self, tr("Insertion failed"), str(e))

    def open_file(self, path):
        try:
            App.openDocument(path)
        except Exception as e:
            App.Console.PrintError(
                tr("Explorer: cannot open {path}: {error}").format(path=path, error=e) + "\n")
            QtWidgets.QMessageBox.warning(
                self, tr("Error"),
                tr("Cannot open\n{path}\n{error}").format(path=path, error=e))

    def open_in_os(self, path):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def closeEvent(self, event):
        self._stop_loading()
        self.timer.stop()
        super().closeEvent(event)


# ----------------------------------------------------------------------
#  Integration in FreeCAD
# ----------------------------------------------------------------------
TAB_TITLE = tr("Local explorer")
DOCK_NAME = "AssemblyInsertComponentDock"


def show_explorer_tab():
    """Explorer in a central tab (like PiStock Local Explorer), click = open."""
    import FreeCADGui as Gui
    mw = Gui.getMainWindow()
    mdi = mw.findChild(QtWidgets.QMdiArea)
    if mdi is None:
        App.Console.PrintError(tr("FreeCAD central area not found.") + "\n")
        return
    for sub in mdi.subWindowList():
        if sub.windowTitle() == TAB_TITLE:
            sub.show()
            mdi.setActiveSubWindow(sub)
            return
    w = ExplorerWidget(mode="open")
    sub = QtWidgets.QMdiSubWindow()
    sub.setWidget(w)
    sub.setWindowTitle(TAB_TITLE)
    sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    mdi.addSubWindow(sub)
    sub.showMaximized()


def show_insert_dock():
    """Explorer in a large floating window over the right half of FreeCAD,
    click = insert into the active assembly / Std_Part. Docked, it ended up
    tabbed under the Tasks panel, far too narrow for the thumbnails; the
    user can still dock it by dragging its title bar."""
    import FreeCADGui as Gui
    mw = Gui.getMainWindow()
    for d in mw.findChildren(QtWidgets.QDockWidget, DOCK_NAME):
        d.show()
        d.raise_()
        d.activateWindow()
        return d
    dock = QtWidgets.QDockWidget(tr("Insert component"), mw)
    dock.setObjectName(DOCK_NAME)
    dock.setWidget(ExplorerWidget(mode="insert", parent=dock))
    mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    dock.setFloating(True)
    g = mw.frameGeometry()
    w, h = max(g.width() // 2, 640), max(g.height() - 120, 480)
    dock.setGeometry(g.x() + g.width() - w - 20, g.y() + 80, w, h)
    dock.show()
    dock.raise_()
    return dock
