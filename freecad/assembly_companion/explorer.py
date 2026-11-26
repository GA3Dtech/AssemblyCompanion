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
import queue
import weakref
import collections
import concurrent.futures

import FreeCAD as App

try:
    from PySide import QtWidgets, QtCore, QtGui
except ImportError:                       # outside FreeCAD (tests)
    from PySide6 import QtWidgets, QtCore, QtGui

from . import docs
from . import library
from . import previews
from . import prefs
from .i18n import tr


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
QLabel#badge { background: rgba(255,255,255,220); border: 1px solid #d2d2d7;
               border-radius: 6px; padding: 0 3px; font-size: 11px; color: #92400e; }
QLabel#tag { color: #92400e; font-size: 11px; }
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


# Folder scan and disk caches live in library.py (no Qt, shared with the
# API); these names stay importable from here.
cache_dir = library.cache_dir
_key = library.cache_key
scan_master = library.scan_master
scan_folder = library.scan_folder
load_scan_cache = library.load_scan_cache
save_scan_cache = library.save_scan_cache


# ----------------------------------------------------------------------
#  Thumbnails (worker threads; QImage is thread-safe, QPixmap is not)
# ----------------------------------------------------------------------
def _is_step(path):
    return os.path.splitext(path)[1].lower() in (".step", ".stp")


extract_fcstd_thumbnail = previews.fcstd_thumbnail

# file kind -> preference that shows it (FreeCAD files are always shown)
KIND_PREFS = {"step": "ExplorerShowStep", "mesh": "ExplorerShowMesh", "pdf": "ExplorerShowPdf"}
NO_PREVIEW = {"step": "STEP", "mesh": "STL / 3MF", "pdf": "PDF"}


def shown_kinds():
    return set(["freecad"] + [k for k, key in KIND_PREFS.items() if prefs.get(key)])


def visible_scan(scan, kinds=None):
    """`scan` with only the files of the kinds shown, empty folders dropped."""
    kinds = shown_kinds() if kinds is None else kinds
    out = {}
    for d, files in (scan or {}).items():
        keep = [f for f in files if previews.kind(f[0]) in kinds]
        if keep:
            out[d] = keep
    return out


def load_thumbnail(cdir, path, mtime, size):
    """Return a small QImage for the file, or None. Uses the local disk cache;
    the .FCStd is unzipped only when it changed since last time. Files without
    thumbnail get a '.none' marker so they are not unzipped again."""
    k = library.thumb_key(path, mtime, size)
    png = os.path.join(cdir, "thumbs", k + ".png")
    none = os.path.join(cdir, "thumbs", k + ".none")
    if os.path.exists(png):
        img = QtGui.QImage(png)
        return None if img.isNull() else img
    if os.path.exists(none):
        return None
    try:
        img = previews.preview_image(path, THUMB_CACHE)
    except Exception:
        img = None
    if img is None or img.isNull():
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

    def __init__(self, path, mtime, size, explorer, tag=""):
        super().__init__()
        self.path, self.mtime, self.size = path, mtime, size
        self.explorer = explorer
        base = os.path.basename(path)
        # FreeCAD files by name; other kinds keep their extension (bracket.stl)
        self.name = os.path.splitext(base)[0] if previews.kind(path) == "freecad" else base
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
        self.badge = QtWidgets.QLabel(self.thumb)        # emoji / #tag over the thumbnail
        self.badge.setObjectName("badge")
        self.badge.move(2, 2)
        self.set_tag(tag)
        lbl = QtWidgets.QLabel(self.name)
        lbl.setObjectName("name")
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.setToolTip(path)

    def set_tag(self, tag):
        self.tag = tag or ""
        self.badge.setText(tag)
        self.badge.adjustSize()
        self.badge.setVisible(bool(tag))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.explorer.main_action(self.path)
        elif event.button() == QtCore.Qt.RightButton:
            self.explorer.card_menu(self, event)

    def set_image(self, img):
        if img is None:
            self.thumb.setText(NO_PREVIEW.get(previews.kind(self.path), tr("(no\nthumbnail)")))
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
        self.blocks = []           # (block widget, [cards], folder rel path), display order
        self.block_map = {}        # norm(folder) -> (block widget, [cards], rel path)
        self.cards_created = 0     # FileCard count (tests: targeted refresh rebuilds few)
        self.generation = 0        # invalidates thumbnails of previous loads
        self.results = queue.Queue()
        self.pool = None
        # Every scan (full or targeted) runs on ONE worker thread and results
        # are applied in submission order: an older full scan can never
        # overwrite a newer targeted refresh.
        self.scan_pool = None
        self.scan_jobs = collections.deque()   # (master, folder, recursive, future)
        self.master = None
        self.current_scan = None
        self._build_ui()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._drain)
        self.timer.start(30)
        self.filter_timer = QtCore.QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.timeout.connect(self.apply_filter)
        # Saves come in bursts (new part: saveAs then save): one read per folder
        self.saved_folders = set()
        self.save_timer = QtCore.QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self._flush_saved)
        _explorers.add(self)
        install_save_observer()
        saved = get_saved_dir()
        if saved:
            self.path_edit.setText(saved)
            if os.path.isdir(saved):
                QtCore.QTimer.singleShot(0, lambda: self.refresh(initial=True))

    # --- UI ------------------------------------------------------------
    def _build_ui(self):
        self.setStyleSheet(STYLE)      # ONE style sheet for every card
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel(tr("Master folder:")))
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.returnPressed.connect(self._master_changed_by_user)
        row.addWidget(self.path_edit, 1)
        b = QtWidgets.QPushButton(tr("Browse…"))
        b.clicked.connect(self._browse)
        row.addWidget(b)
        b = QtWidgets.QPushButton(tr("Refresh all"))
        b.setToolTip(tr("Read the whole folder again (unchanged thumbnails stay cached). "
                        "Right-click a folder header to refresh only that folder."))
        b.clicked.connect(self.refresh)
        row.addWidget(b)
        main.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText(tr("Filter by file or folder name, or #tag…"))
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
        self.favs_only = QtWidgets.QCheckBox(tr("Favorites only"))
        self.favs_only.toggled.connect(lambda *_: self.apply_filter())
        row.addWidget(self.favs_only)
        self.favs_button = QtWidgets.QToolButton()
        self.favs_button.setText("★")
        self.favs_button.setToolTip(tr("Favorite folders (right-click a folder header to add "
                                       "one)"))
        self.favs_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.favs_menu = QtWidgets.QMenu(self.favs_button)
        self.favs_menu.aboutToShow.connect(self._fill_favorites_menu)
        self.favs_button.setMenu(self.favs_menu)
        row.addWidget(self.favs_button)
        main.addLayout(row)

        self.freeze_check = QtWidgets.QCheckBox(tr("Freeze on insertion"))
        self.freeze_check.setToolTip(tr("Insert the part, then freeze it at once "
                                        "(Assembly Companion)"))
        self.freeze_check.setChecked(get_freeze_on_insert())
        self.freeze_check.toggled.connect(set_freeze_on_insert)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.freeze_check)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel(tr("Also show:")))
        self.kind_checks = {}
        for kind_, label in (("step", "STEP"), ("mesh", "STL / 3MF"), ("pdf", "PDF")):
            cb = QtWidgets.QCheckBox(label)
            cb.setToolTip(tr("Show these files besides the FreeCAD files"))
            cb.setChecked(bool(prefs.get(KIND_PREFS[kind_])))
            cb.toggled.connect(lambda on, k=kind_: self._show_kind(k, on))
            row.addWidget(cb)
            self.kind_checks[kind_] = cb
        main.addLayout(row)

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
            self._master_changed_by_user()

    # --- Scan ----------------------------------------------------------
    def _master_changed_by_user(self):
        """The user typed or browsed another folder: offer to delete the
        cache of the previous one (only then: never during a refresh)."""
        master = self.path_edit.text().strip()
        old = prefs.get(PARAM_DIR_KEY)      # this addon's setting, not PiStock's
        if master and old and os.path.isdir(master) and \
                library.norm(old) != library.norm(master):
            prefs.offer_clear_master_cache(old, self)
        self.refresh()

    def refresh(self, initial=False):
        """Show the folder (from the disk cache when there is one), then
        queue a full rescan. At opening (`initial`) the rescan follows the
        ExplorerFullScan preference: files created and saved from FreeCAD
        are refreshed one folder at a time anyway."""
        master = os.path.normpath(self.path_edit.text().strip()) \
            if self.path_edit.text().strip() else ""
        self.cdir = cache_dir()             # the cache folder may have changed
        set_saved_dir(master)
        if not master or not os.path.isdir(master):
            self.master = None
            self._show_message(tr("Folder not found: {path}").format(path=master) if master else
                               tr("Enter a master folder above, then click “Refresh all”."))
            return
        cached = None
        if master != self.master or self.current_scan is None:
            self.master = master
            self.scan_jobs.clear()                # results of another folder are dropped
            cached = load_scan_cache(master)
            if cached:
                self._build(master, cached)       # instant display from cache
            else:
                self._show_message(tr("Scanning the folder…"))
        if initial and cached and not _full_scan_on_open(master):
            return
        self.queue_scan(master, True)
        self.status.setText(self.status.text() + "   " + tr("(checking the folder…)"))

    def refresh_folder(self, folder, recursive=False):
        """Targeted refresh: read only `folder` (and its subfolders)."""
        if self.master and library.is_inside(folder, self.master):
            self.queue_scan(os.path.normpath(folder), recursive)

    def refresh_file(self, path):
        """A file was created or saved: refresh its folder if it is shown."""
        if path and path.lower().endswith(".fcstd"):
            folder = os.path.dirname(os.path.abspath(path))
            if self.master and library.is_inside(folder, self.master):
                self.saved_folders.add(folder)
                self.save_timer.start(250)

    def _flush_saved(self):
        folders, self.saved_folders = sorted(self.saved_folders), set()
        for folder in folders:
            self.refresh_folder(folder, False)

    def queue_scan(self, folder, recursive):
        key = (library.norm(folder), recursive)
        for _m, f, r, fut in self.scan_jobs:      # same request still waiting: once is enough
            if (library.norm(f), r) == key and not fut.running() and not fut.done():
                return
        if self.scan_pool is None:
            self.scan_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = self.scan_pool.submit(scan_folder, folder, recursive)
        self.scan_jobs.append((self.master, folder, recursive, fut))

    def _check_scan(self):
        while self.scan_jobs and self.scan_jobs[0][3].done():
            master, folder, recursive, fut = self.scan_jobs.popleft()
            if master != self.master:
                continue
            try:
                partial = fut.result()
            except Exception as e:
                self.status.setText(tr("Scan error: {error}").format(error=e))
                continue
            self._apply_scan(folder, partial, recursive)

    def _apply_scan(self, folder, partial, recursive):
        master = self.master
        new, changed = library.merge_scan(self.current_scan or {}, folder, partial, recursive)
        save_scan_cache(master, new)
        if recursive and library.norm(folder) == library.norm(master):
            _scanned_this_session.add(library.norm(master))
        if self.current_scan is None or not self.block_map or not new:
            self._build(master, new)
        elif changed:
            self._update_folders(master, new, changed)
        else:
            self.status.setText(self._summary(new))

    # --- Display -------------------------------------------------------
    def _summary(self, scan):
        total = sum(len(v) for v in scan.values())
        text = tr("{files} file(s) in {folders} folder(s)").format(files=total, folders=len(scan))
        missing = library.missing_favorites(self.master) if self.master else []
        if missing:
            text += "   " + tr("({n} favorite folder(s) not found: see ★)").format(n=len(missing))
        return text

    def _show_message(self, text):
        self._stop_loading()
        self._new_container()
        self.cards, self.blocks, self.block_map, self.current_scan = {}, [], {}, None
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
        """Full rebuild of the view (first display, other master folder)."""
        self._stop_loading()
        if not scan:
            self._show_message(tr("No FreeCAD file (.FCStd) under this folder."))
            self.current_scan = scan
            return
        self.current_scan = scan
        scan = visible_scan(scan)
        scroll_pos = self.scroll.verticalScrollBar().value()
        self._new_container()
        self.cards, self.block_map = {}, {}
        self.tree_container.setUpdatesEnabled(False)
        new_cards = []
        for d in self._view_order(master, scan):
            block, cards, rel = self._make_block(master, d, scan.get(d, []))
            self.tree_layout.addWidget(block)
            self.block_map[library.norm(d)] = (block, cards, rel)
            new_cards += cards
        self.tree_layout.addStretch()
        self.tree_container.setUpdatesEnabled(True)
        self._sync_blocks(master, scan)
        QtCore.QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(scroll_pos))
        self.status.setText(self._summary(scan))
        self.apply_filter()
        self._load_thumbnails(new_cards)

    def _update_folders(self, master, scan, changed):
        """Incremental update: rebuild, insert or remove only the blocks of
        `changed` folders (and parents that appear / disappear). Other blocks
        keep their cards and thumbnails; scroll position and filter stay."""
        self.current_scan = scan
        scan = visible_scan(scan)
        wanted = self._view_order(master, scan)
        wanted_keys = {library.norm(d) for d in wanted}
        changed_keys = {library.norm(d) for d in changed}
        self.tree_container.setUpdatesEnabled(False)
        for key in [k for k in self.block_map if k not in wanted_keys]:
            self._drop_block(key)
        new_cards = []
        for i, d in enumerate(wanted):
            key = library.norm(d)
            if key in self.block_map and key not in changed_keys:
                continue
            block, cards, rel = self._make_block(master, d, scan.get(d, []))
            if key in self.block_map:
                i = self.tree_layout.indexOf(self.block_map[key][0])
                self._drop_block(key)
            self.tree_layout.insertWidget(i, block)
            self.block_map[key] = (block, cards, rel)
            new_cards += cards
        self.tree_container.setUpdatesEnabled(True)
        self._sync_blocks(master, scan)
        self.apply_filter()
        self._load_thumbnails(new_cards)

    def _drop_block(self, key):
        block, cards, _rel = self.block_map.pop(key)
        for c in cards:
            if self.cards.get(c.path) is c:
                del self.cards[c.path]
        self.tree_layout.removeWidget(block)
        block.hide()
        block.deleteLater()

    def _sync_blocks(self, master, scan):
        """self.blocks (used by the filter) in display order."""
        self.blocks = [self.block_map[library.norm(d)]
                       for d in self._view_order(master, visible_scan(scan))
                       if library.norm(d) in self.block_map]

    def _load_thumbnails(self, cards):
        """Cached thumbnails are fast, missing ones are unzipped in parallel."""
        if not cards:
            return
        if self.pool is None:
            self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS)
        gen = self.generation
        for card in cards:
            self.pool.submit(self._job, gen, card.path, card.mtime, card.size)

    def _job(self, gen, path, mtime, size):
        if gen != self.generation:
            return
        try:
            img = load_thumbnail(self.cdir, path, mtime, size)
        except Exception:
            img = None
        self.results.put((gen, path, mtime, img))

    def _drain(self):
        """GUI timer: apply finished scans and thumbnails, a batch at a time."""
        self._check_scan()
        for _ in range(BATCH_PER_TICK):
            try:
                gen, path, mtime, img = self.results.get_nowait()
            except queue.Empty:
                return
            if gen != self.generation:
                continue
            card = self.cards.get(path)
            if card is not None and card.mtime == mtime:
                card.set_image(img)

    def _view_order(self, master, scan):
        """Folders in display order, favourites of this library first."""
        favs = [f for f in library.favorites() if library.is_inside(f, master)]
        return library.order_with_favorites(library.view_folders(master, scan), favs)

    def _make_block(self, master, path, files):
        pinned = library.is_favorite(path)
        depth = 0 if pinned else len(library.folder_sort_key(master, path))
        block = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(block)
        v.setSpacing(4)
        v.setContentsMargins(depth * INDENT_PX, 0, 0, 0)
        head = QtWidgets.QWidget()
        head.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        head.customContextMenuRequested.connect(
            lambda pos, p=path, w=head: self.folder_menu(p, w.mapToGlobal(pos)))
        header = QtWidgets.QHBoxLayout(head)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        icon = QtWidgets.QLabel()
        sp = getattr(getattr(QtWidgets.QStyle, "StandardPixmap", QtWidgets.QStyle), "SP_DirIcon")
        icon.setPixmap(self.style().standardIcon(sp).pixmap(16, 16))
        header.addWidget(icon)
        is_master = library.norm(path) == library.norm(master)
        rel = "" if is_master else os.path.relpath(path, master)
        name = tr("(master)") if is_master else os.path.basename(path)
        btn = QtWidgets.QPushButton(("★ " + name) if pinned else name)
        btn.setObjectName("folder")
        btn.setFlat(True)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setToolTip(tr("Open this folder in the file manager. "
                          "Right-click: refresh this folder."))
        btn.clicked.connect(lambda checked=False, p=path: self.open_in_os(p))
        btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, p=path, w=btn: self.folder_menu(p, w.mapToGlobal(pos)))
        header.addWidget(btn)
        if rel:
            r = QtWidgets.QLabel(rel)
            r.setObjectName("rel")
            header.addWidget(r)
        tag = library.tag_of(path)
        block.ac_tag = tag.lower()          # searched by the filter
        if tag:
            t = QtWidgets.QLabel(tag)
            t.setObjectName("tag")
            header.addWidget(t)
        header.addStretch()
        cards = []
        if files:
            c = QtWidgets.QLabel(str(len(files)))
            c.setObjectName("count")
            header.addWidget(c)
        v.addWidget(head)
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
            tags = library.tags()           # read once per block, not once per card
            for fpath, mtime, size in files:
                card = FileCard(fpath, mtime, size, self, tags.get(library.norm(fpath), ""))
                self.cards_created += 1
                h.addWidget(card)
                self.cards[fpath] = card
                cards.append(card)
            h.addStretch()
            strip.setWidget(inner)
            v.addWidget(strip)
        return block, cards, rel.lower()

    def folder_menu(self, path, global_pos):
        menu = QtWidgets.QMenu(self)
        if library.is_favorite(path):
            menu.addAction(tr("Remove from favorites"), lambda: self.toggle_favorite(path))
        else:
            menu.addAction(tr("Add to favorites"), lambda: self.toggle_favorite(path))
        menu.addAction(tr("Tag (emoji or #tag)…"), lambda: self.edit_tag(path))
        menu.addSeparator()
        menu.addAction(tr("Refresh this folder"),
                       lambda: self.refresh_folder(path, False))
        menu.addAction(tr("Refresh this folder and its subfolders"),
                       lambda: self.refresh_folder(path, True))
        menu.addSeparator()
        menu.addAction(tr("Open in the file manager"), lambda: self.open_in_os(path))
        menu.exec(global_pos) if hasattr(menu, "exec") else menu.exec_(global_pos)

    def _show_kind(self, kind_, on):
        prefs.put(KIND_PREFS[kind_], bool(on))
        if self.master and self.current_scan is not None:
            self._build(self.master, self.current_scan)     # thumbnails come from the cache

    # --- Favourites and tags -------------------------------------------
    def toggle_favorite(self, path):
        library.set_favorite(path, not library.is_favorite(path))
        self._refresh_block(path)

    def _refresh_block(self, folder):
        """Rebuild only the block of `folder` (moved to its new place when it
        becomes / stops being a favourite); the other blocks keep their
        cards and thumbnails."""
        if self.master and self.current_scan is not None and self.block_map:
            self._update_folders(self.master, self.current_scan, [folder])

    def edit_tag(self, path):
        text, ok = QtWidgets.QInputDialog.getText(
            self, tr("Tag"), tr("Emoji or short #tag shown on the thumbnail (empty: none):"),
            text=library.tag_of(path))
        if ok:
            self.set_tag(path, text)

    def set_tag(self, path, text):
        tag = library.set_tag(path, text)
        card = self.cards.get(path)
        if card is not None:
            card.set_tag(tag)
            self.apply_filter()
        else:
            self._refresh_block(path)
        return tag

    def _fill_favorites_menu(self):
        m = self.favs_menu
        m.clear()
        shown = 0
        for f in library.favorites():
            if self.master and not library.is_inside(f, self.master):
                continue
            if os.path.isdir(f):
                m.addAction("★ " + os.path.basename(f) or f, lambda p=f: self.show_folder(p))
            else:
                a = m.addAction(tr("{path} (not found)").format(path=f))
                a.setEnabled(False)
            shown += 1
        if not shown:
            a = m.addAction(tr("No favorite folder yet: right-click a folder header."))
            a.setEnabled(False)
        missing = library.missing_favorites(self.master)
        if missing:
            m.addSeparator()
            m.addAction(tr("Remove the favorites not found"), self._remove_missing_favorites)

    def _remove_missing_favorites(self):
        for f in library.missing_favorites(self.master):
            library.set_favorite(f, False)

    def show_folder(self, path):
        entry = self.block_map.get(library.norm(path))
        if entry is not None:
            self.scroll.ensureWidgetVisible(entry[0], 0, 0)

    # --- Filter --------------------------------------------------------
    def apply_filter(self):
        txt = self.filter_edit.text().strip().lower()
        shown = 0
        self.tree_container.setUpdatesEnabled(False)
        only_favs = self.favs_only.isChecked()
        fav_rels = set()
        if only_favs and self.master:
            for f in library.favorites():
                if library.is_inside(f, self.master):
                    r = os.path.relpath(f, self.master)
                    fav_rels.add("" if r == "." else r.lower())
        for block, cards, rel in self.blocks:
            if only_favs and rel not in fav_rels:
                block.setVisible(False)
                for c in cards:
                    c.setVisible(False)
                continue
            if not txt:
                for c in cards:
                    c.setVisible(True)
                block.setVisible(True)
                shown += len(cards)
                continue
            # names and tags (#tag, emoji) of the folder and of the files
            folder_match = txt in rel or txt in getattr(block, "ac_tag", "")
            n = 0
            for c in cards:
                ok = folder_match or txt in c.name.lower() or txt in c.tag.lower()
                c.setVisible(ok)
                n += ok
            block.setVisible(n > 0 or folder_match)
            shown += n
        self.tree_container.setUpdatesEnabled(True)
        if txt and self.current_scan:
            self.status.setText(tr("{n} file(s) match “{text}”").format(n=shown, text=txt))
        elif self.current_scan:
            self.status.setText(self._summary(self.current_scan))

    # --- Actions -------------------------------------------------------
    def main_action(self, path):
        if self.mode == "insert" and previews.kind(path) in ("freecad", "step"):
            self.insert_file(path)
        else:
            self.open_file(path)

    def card_menu(self, card, event):
        menu = QtWidgets.QMenu(self)
        if previews.kind(card.path) in ("freecad", "step"):
            menu.addAction(tr("Insert into the active assembly"),
                           lambda: self.insert_file(card.path))
        menu.addAction(tr("Open"), lambda: self.open_file(card.path))
        menu.addAction(tr("Open folder"), lambda: self.open_in_os(os.path.dirname(card.path)))
        menu.addSeparator()
        menu.addAction(tr("Tag (emoji or #tag)…"), lambda: self.edit_tag(card.path))
        pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") \
            else event.globalPos()
        menu.exec(pos) if hasattr(menu, "exec") else menu.exec_(pos)

    def insert_file(self, path):
        if _is_step(path):                  # imported as a part, see step_import.py
            try:
                from . import step_import
                r = step_import.import_command(path)
                if r is not None:
                    self.status.setText(tr("“{name}” inserted.").format(
                        name=os.path.basename(path)))
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, tr("Insertion failed"), str(e))
            return
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
            k = previews.kind(path)
            if k == "step":
                import ImportGui
                ImportGui.open(path)
                return
            if k == "mesh":
                import Mesh
                Mesh.open(path)
                return
            if k == "pdf":
                docs.open_in_file_manager(path)     # the system PDF viewer
                return
            App.openDocument(path)
        except Exception as e:
            App.Console.PrintError(
                tr("Explorer: cannot open {path}: {error}").format(path=path, error=e) + "\n")
            QtWidgets.QMessageBox.warning(
                self, tr("Error"),
                tr("Cannot open\n{path}\n{error}").format(path=path, error=e))

    def open_in_os(self, path):
        docs.open_in_file_manager(path)

    def closeEvent(self, event):
        self._stop_loading()
        self.timer.stop()
        self.scan_jobs.clear()
        if self.scan_pool is not None:
            self.scan_pool.shutdown(wait=False, cancel_futures=True)
            self.scan_pool = None
        _explorers.discard(self)
        super().closeEvent(event)


# ----------------------------------------------------------------------
#  Targeted refresh from FreeCAD (saves, new parts)
# ----------------------------------------------------------------------
_explorers = weakref.WeakSet()      # open explorer widgets (tab and dock)
_scanned_this_session = set()       # norm(master) fully scanned since FreeCAD started
_save_observer = None


def _full_scan_on_open(master):
    """ExplorerFullScan preference: full rescan when an explorer opens with
    a cached view ("always", "session" = once per FreeCAD session, "manual")."""
    mode = prefs.get("ExplorerFullScan")
    if mode == "manual":
        return False
    if mode == "session":
        return library.norm(master) not in _scanned_this_session
    return True


def refresh_saved_file(path):
    """Refresh the folder of `path` in every open explorer showing it."""
    for w in list(_explorers):
        try:
            w.refresh_file(path)
        except RuntimeError:            # Qt object already deleted
            _explorers.discard(w)


class _SaveObserver(object):
    """App document observer: a document saved under the master folder
    (new part, new revision, any save) refreshes only its folder."""

    def slotFinishSaveDocument(self, doc, filename):
        try:
            refresh_saved_file(filename or getattr(doc, "FileName", ""))
        except Exception as exc:
            App.Console.PrintLog("Assembly Companion explorer: %s\n" % exc)


def install_save_observer():
    global _save_observer
    if _save_observer is None:
        _save_observer = _SaveObserver()
        App.addDocumentObserver(_save_observer)


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
