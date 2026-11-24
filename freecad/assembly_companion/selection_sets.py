# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - selection sets
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
# ---------------------------------------------------------------------------
#  selection_sets.py (Assembly Companion)
#  Docked panel to create, edit and reuse named selection sets in large
#  assemblies (STEP files exploded into hundreds of parts, old assemblies,
#  hidden parts, repeated selections while modelling).
#
#  - Sets are stored INSIDE the document ("Selection sets" group), so they
#    are saved with the .FCStd file. Parts are never moved.
#  - Each member is stored by its full path (root + subpath), which tells
#    apart the different instances of the same part (App::Link).
#  - Works with FreeCAD 0.21, 1.0, 1.1 and 26.x (PySide2 or PySide6).
#
#  User-facing texts are in English, translated through i18n.tr().
# ---------------------------------------------------------------------------

__Title__ = "Selection sets"
__Author__ = "GA3Dtech"
__Version__ = "1.0"
__Comment__ = "Manager of named selection sets for large assemblies"

import re

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

try:
    from PySide import QtWidgets
except ImportError:  # older versions: widgets live in QtGui
    QtWidgets = QtGui

try:
    import Part
except ImportError:
    Part = None

from . import prefs
from .i18n import tr

DOCK_NAME = "JeuxDeSelectionDock"
GROUP_MARK = "SelectionSetsGroup"
PROP = "SelectionSetMembers"
SKIP_TYPES = ("App::Origin", "App::Line", "App::Plane", "App::Point",
              "App::OriginFeature", "App::LocalCoordinateSystem")
TRANSPARENCY = 85


# --------------------------------------------------------------------------
#  Qt5 / Qt6 compatibility
# --------------------------------------------------------------------------
def _enum(owner, group, name):
    """Return a Qt enum value, Qt6 (scoped) or Qt5 style."""
    g = getattr(owner, group, None)
    if g is not None and hasattr(g, name):
        return getattr(g, name)
    return getattr(owner, name)


def _exec(dialog):
    fn = getattr(dialog, "exec_", None) or getattr(dialog, "exec")
    return fn()


USER_ROLE = _enum(QtCore.Qt, "ItemDataRole", "UserRole")
WAIT_CURSOR = _enum(QtCore.Qt, "CursorShape", "WaitCursor")
RIGHT_AREA = _enum(QtCore.Qt, "DockWidgetArea", "RightDockWidgetArea")
BTN_OK = _enum(QtWidgets.QDialogButtonBox, "StandardButton", "Ok")
BTN_CANCEL = _enum(QtWidgets.QDialogButtonBox, "StandardButton", "Cancel")
MB_YES = _enum(QtWidgets.QMessageBox, "StandardButton", "Yes")
MB_NO = _enum(QtWidgets.QMessageBox, "StandardButton", "No")


class _Busy(object):
    """Busy cursor during long operations."""
    def __enter__(self):
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(WAIT_CURSOR))
        return self

    def __exit__(self, *a):
        QtWidgets.QApplication.restoreOverrideCursor()
        return False


# --------------------------------------------------------------------------
#  Paths: a member = "RootName|Sub.Path." (internal names)
# --------------------------------------------------------------------------
def make_key(root, sub):
    return root + "|" + (sub or "")


def split_key(k):
    root, _, sub = k.partition("|")
    return root, sub


def dedupe(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def strip_element(obj, sub):
    """Remove the element part (Face3, Edge12...) of a subpath."""
    if not sub:
        return ""
    if sub.endswith("."):
        return sub
    try:
        res = obj.resolve(sub)
        elem = res[3] if len(res) > 3 else ""
        if elem and sub.endswith(elem):
            return sub[:-len(elem)]
    except Exception:
        pass
    i = sub.rfind(".")
    return sub[:i + 1] if i >= 0 else ""


_ELEMENT = re.compile(r"^(Face|Edge|Vertex)\d+$")


def element_of(k):
    """Element name of a member ("Face6"), "" for a whole object."""
    sub = split_key(k)[1]
    if not sub or sub.endswith("."):
        return ""
    last = sub.rsplit(".", 1)[-1]
    return last if _ELEMENT.match(last) else ""


def object_key(k):
    """Member without its element: the object carrying the face / edge."""
    e = element_of(k)
    if not e:
        return k
    r, s = split_key(k)
    return make_key(r, s[:-len(e)])


def element_sub(obj, sub):
    """Subname of a selected element without mapped topological names
    (";#..."), which do not resolve once the topology is rebuilt."""
    from .freeze import decouper_sub
    if ";" not in sub:
        return sub
    objets, _mapped, elem = decouper_sub(sub)
    return ".".join(objets) + "." + elem if elem else strip_element(obj, sub)


def path_names(sub):
    return [n for n in (sub or "").split(".") if n]


def path_objects(doc, k):
    """Objects along the path [root, ..., leaf], or None (for an element
    member: the object carrying it)."""
    rname, sub = split_key(object_key(k))
    root = doc.getObject(rname)
    if root is None:
        return None
    if not sub:
        return [root]
    names = path_names(sub)
    objs = None
    try:
        objs = list(root.getSubObjectList(sub))
    except Exception:
        objs = None
    if objs:
        idx = [i for i, o in enumerate(objs) if o.Name == names[-1]]
        if idx:
            objs = objs[:idx[-1] + 1]
    if not objs or len(objs) < 2:
        objs = [root]
        for n in names:
            o = doc.getObject(n)
            if o is None:
                return None
            objs.append(o)
    return objs


def path_ancestors(doc, k):
    """Path objects actually named in the subpath (root included)."""
    objs = path_objects(doc, k)
    if not objs:
        return None
    names = set(path_names(split_key(k)[1]))
    return [o for i, o in enumerate(objs) if i == 0 or o.Name in names]


def is_skipped(o):
    try:
        if o.TypeId in SKIP_TYPES:
            return True
        props = o.PropertiesList
        return PROP in props or GROUP_MARK in props
    except Exception:
        return True


def is_container(o):
    try:
        if o.isDerivedFrom("PartDesign::Body"):
            return False
    except Exception:
        pass
    if o.TypeId in ("App::Link", "App::LinkGroup", "App::LinkElement"):
        return True
    try:
        return bool(o.hasExtension("App::GroupExtension"))
    except Exception:
        return False


def child_subs(o):
    try:
        subs = o.getSubObjects()
    except Exception:
        return []
    out = []
    doc = o.Document
    for s in subs:
        if not s.endswith("."):
            s += "."
        child = doc.getObject(s.split(".")[0])
        if child is not None and is_skipped(child):
            continue
        out.append(s)
    return out


def is_shape_leaf(o):
    return hasattr(o, "Shape") or o.TypeId.startswith("App::Link")


def walk_leaves(doc, k, out, depth=0):
    objs = path_objects(doc, k)
    if not objs:
        return
    o = objs[-1]
    if depth < 60 and is_container(o):
        subs = child_subs(o)
        if subs:
            r, s = split_key(k)
            for c in subs:
                walk_leaves(doc, make_key(r, s + c), out, depth + 1)
            return
        if not o.TypeId.startswith("App::Link"):
            return  # empty group
    if is_shape_leaf(o):
        out.append(k)


def all_leaves(doc):
    out = []
    for o in doc.RootObjects:
        if is_skipped(o):
            continue
        walk_leaves(doc, make_key(o.Name, ""), out)
    return dedupe(out)


def expand(doc, keys):
    """Members as individual parts; element members are kept as they are."""
    out = []
    for k in keys:
        if element_of(k):
            out.append(k)
        else:
            walk_leaves(doc, k, out)
    return dedupe(out)


def leaf_of(doc, k):
    objs = path_objects(doc, k)
    return objs[-1] if objs else None


def oid(o):
    """Identity of an object across documents (names repeat between files)."""
    return (o.Document.Name, o.Name)


def visibility_chain(doc, k):
    """Objects whose Visibility drives the display of member k, from the root
    down to its "visibility target". The chain stops at the first Link or
    Body and never leaves `doc`: changing the Visibility of what lies inside
    a Link (objects of a source file opened in the background, features of a
    Body, children shared by several Links) can crash FreeCAD, and would
    hide the part in every other instance anyway."""
    chain = []
    for o in path_ancestors(doc, k) or []:
        if o.Document is not doc:
            break
        chain.append(o)
        if o.TypeId.startswith("App::Link") or o.isDerivedFrom("PartDesign::Body"):
            break
    return chain


def visibility_target(doc, k):
    chain = visibility_chain(doc, k)
    return chain[-1] if chain else None


def show_path(doc, k):
    chain = visibility_chain(doc, k)
    if not chain:
        return False
    for o in chain:
        try:
            if not o.Visibility:
                o.Visibility = True
        except Exception:
            pass
    return True


def path_is_visible(doc, k):
    chain = visibility_chain(doc, k)
    if not chain:
        return False
    try:
        return all(o.Visibility for o in chain)
    except Exception:
        return True


def leave_assembly_edit(doc):
    """Leave the edit mode of an assembly: in that mode a click in the 3D view
    picks and drags whole parts, so faces, edges and vertices cannot be
    selected. Returns True when an assembly was left."""
    try:
        gdoc = Gui.getDocument(doc.Name)
        vp = gdoc.getInEdit()
        if vp is not None and vp.Object.isDerivedFrom("Assembly::AssemblyObject"):
            gdoc.resetEdit()
            return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------
#  Storage of the sets inside the document
# --------------------------------------------------------------------------
def find_group(doc, create=False):
    for o in doc.Objects:
        if GROUP_MARK in o.PropertiesList:
            return o
    if not create:
        return None
    g = doc.addObject("App::DocumentObjectGroup", "Jeux_de_selection")
    g.addProperty("App::PropertyBool", GROUP_MARK, "Selection sets",
                  "Marker of the selection sets group")
    setattr(g, GROUP_MARK, True)
    g.Label = tr("Selection sets")
    return g


def list_sets(doc):
    return [o for o in doc.Objects if PROP in o.PropertiesList]


def get_members(s):
    return list(getattr(s, PROP))


def set_members(s, keys):
    setattr(s, PROP, dedupe(keys))
    try:
        s.purgeTouched()
    except Exception:
        pass


def set_shape(doc, s):
    """SubShapeBinder made from the set `s` ("Shape for TechDraw"), or None."""
    for o in doc.Objects:
        if "SetShapeOf" in o.PropertiesList and o.SetShapeOf == s.Name:
            return o
    return None


def create_set(doc, label, keys):
    g = find_group(doc, create=True)
    s = doc.addObject("App::FeaturePython", "JeuSel")
    s.addProperty("App::PropertyStringList", PROP, "Selection set",
                  "Members: RootName|sub.path.")
    s.Label = label
    set_members(s, keys)
    g.addObject(s)
    try:
        g.purgeTouched()
    except Exception:
        pass
    return s


def selection_keys(doc, elements=False):
    """Members of the current selection: whole objects, or with `elements`
    the selected faces / edges / vertices themselves."""
    out = []
    for so in Gui.Selection.getSelectionEx("", 0):
        try:
            if so.DocumentName != doc.Name:
                continue
        except Exception:
            pass
        root = so.Object
        if is_skipped(root):
            continue
        subs = so.SubElementNames or ("",)
        for sub in subs:
            if elements and sub and not sub.endswith("."):
                out.append(make_key(root.Name, element_sub(root, sub)))
            else:
                out.append(make_key(root.Name, strip_element(root, sub)))
    return dedupe(out)


def select_keys(doc, keys, clear=True):
    if clear:
        Gui.Selection.clearSelection()
    missing = 0
    for k in keys:
        if path_objects(doc, k) is None:
            missing += 1
            continue
        r, s = split_key(k)
        try:
            Gui.Selection.addSelection(doc.Name, r, s)
        except Exception:
            missing += 1
    return missing


# --------------------------------------------------------------------------
#  "Create by filter" dialog
# --------------------------------------------------------------------------
class FilterDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(FilterDialog, self).__init__(parent)
        # Built here, not at class level, so tr() runs after the language is known
        self.TARGETS = [tr("New set"), tr("Add to current set"),
                        tr("Select only")]
        self.setWindowTitle(tr("Filter parts"))
        form = QtWidgets.QFormLayout(self)

        self.text = QtWidgets.QLineEdit()
        self.text.setPlaceholderText(tr("e.g. screw, M6, bearing…  (empty = all)"))
        self.regex = QtWidgets.QCheckBox(tr("Regular expression"))
        self.parents = QtWidgets.QCheckBox(
            tr("Also search the names of parent sub-assemblies"))
        self.parents.setChecked(True)

        def spin(maxv, suffix):
            sp = QtWidgets.QDoubleSpinBox()
            sp.setRange(0, maxv)
            sp.setDecimals(1)
            sp.setSuffix(suffix)
            sp.setSpecialValueText("—")
            return sp

        self.smin = spin(1e7, " mm")
        self.smax = spin(1e7, " mm")
        self.vmin = spin(1e13, " mm³")
        self.vmax = spin(1e13, " mm³")
        self.visible = QtWidgets.QCheckBox(tr("Visible parts only"))
        self.target = QtWidgets.QComboBox()
        self.target.addItems(self.TARGETS)

        form.addRow(tr("Name contains:"), self.text)
        form.addRow("", self.regex)
        form.addRow("", self.parents)
        form.addRow(tr("Min size (box diag.):"), self.smin)
        form.addRow(tr("Max size (box diag.):"), self.smax)
        form.addRow(tr("Min volume:"), self.vmin)
        form.addRow(tr("Max volume:"), self.vmax)
        form.addRow("", self.visible)
        form.addRow(tr("Result:"), self.target)

        bb = QtWidgets.QDialogButtonBox(BTN_OK | BTN_CANCEL)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def run_filter(self, doc):
        txt = self.text.text().strip()
        matcher = None
        if txt:
            if self.regex.isChecked():
                rx = re.compile(txt, re.IGNORECASE)
                matcher = lambda s: rx.search(s) is not None
            else:
                low = txt.lower()
                matcher = lambda s: low in s.lower()
        smin, smax = self.smin.value(), self.smax.value()
        vmin, vmax = self.vmin.value(), self.vmax.value()
        need_shape = bool(smin or smax or vmin or vmax)
        only_vis = self.visible.isChecked()
        use_parents = self.parents.isChecked()

        result = []
        for k in all_leaves(doc):
            anc = path_ancestors(doc, k)
            if not anc:
                continue
            leaf = leaf_of(doc, k) or anc[-1]
            if only_vis and not path_is_visible(doc, k):
                continue
            if matcher:
                labels = [o.Label for o in anc] if use_parents else [leaf.Label]
                if leaf.Label not in labels:
                    labels.append(leaf.Label)
                if not any(matcher(l) for l in labels):
                    continue
            if need_shape:
                if Part is None:
                    continue
                r, s = split_key(k)
                try:
                    shp = Part.getShape(doc.getObject(r), s)
                    if shp.isNull():
                        continue
                    diag = shp.BoundBox.DiagonalLength
                    vol = abs(shp.Volume)
                except Exception:
                    continue
                if smin and diag < smin:
                    continue
                if smax and diag > smax:
                    continue
                if vmin and vol < vmin:
                    continue
                if vmax and vol > vmax:
                    continue
            result.append(k)
        return result


# --------------------------------------------------------------------------
#  Main panel
# --------------------------------------------------------------------------
class SelectionSetsPanel(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(SelectionSetsPanel, self).__init__(parent)
        self._signature = None
        self._saved_view = {}   # (doc, obj) -> (Transparency, Selectable)
        self._build_ui()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh_if_changed)
        self.timer.start(1000)
        self.refresh()

    # ---------- user interface ----------
    def _btn(self, text, tip, slot):
        b = QtWidgets.QPushButton(text)
        b.setToolTip(tip)
        b.clicked.connect(slot)
        return b

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        self.list = QtWidgets.QListWidget()
        self.list.setToolTip(tr("Double-click: select the set"))
        self.list.itemDoubleClicked.connect(lambda *_: self.select_set())
        lay.addWidget(self.list, 1)

        self.elements = QtWidgets.QCheckBox(tr("Keep faces, edges and vertices"))
        self.elements.setToolTip(tr(
            "Checked: New / Add / Remove / Replace store the selected faces, edges and "
            "vertices themselves, and selecting the set selects them again (useful for "
            "TechDraw). Unchecked: a face designates its whole part."))
        self.elements.setChecked(prefs.get("SelectionSetsElements"))
        self.elements.toggled.connect(lambda on: prefs.put("SelectionSetsElements", on))
        lay.addWidget(self.elements)

        g1 = QtWidgets.QGroupBox(tr("Compose"))
        l1 = QtWidgets.QGridLayout(g1)
        l1.addWidget(self._btn(tr("New"), tr("Create a set from the current selection"), self.new_set), 0, 0)
        l1.addWidget(self._btn(tr("+ Add"), tr("Add the current selection to the set"), self.add_to_set), 0, 1)
        l1.addWidget(self._btn(tr("− Remove"), tr("Remove the current selection from the set"), self.remove_from_set), 0, 2)
        l1.addWidget(self._btn(tr("Replace"), tr("Replace the content of the set with the current selection"), self.replace_set), 1, 0)
        l1.addWidget(self._btn(tr("Filter…"), tr("Create / extend a set by name, size, volume"), self.filter_set), 1, 1)
        l1.addWidget(self._btn(tr("Clean"), tr("Remove parts that no longer exist from the set"), self.clean_set), 1, 2)
        l1.addWidget(self._btn(tr("Rename"), tr("Rename the set"), self.rename_set), 2, 0)
        l1.addWidget(self._btn(tr("Duplicate"), tr("Copy the set"), self.duplicate_set), 2, 1)
        l1.addWidget(self._btn(tr("Delete"), tr("Delete the set (not the parts)"), self.delete_set), 2, 2)
        lay.addWidget(g1)

        g2 = QtWidgets.QGroupBox(tr("Use"))
        l2 = QtWidgets.QGridLayout(g2)
        l2.addWidget(self._btn(tr("Select"), tr("Replace the selection with the set"), self.select_set), 0, 0)
        l2.addWidget(self._btn(tr("Select +"), tr("Add the set to the current selection"), lambda: self.select_set(clear=False)), 0, 1)
        l2.addWidget(self._btn(tr("Zoom"), tr("Select the set and fit the view to it"), self.zoom_set), 0, 2)
        l2.addWidget(self._btn(tr("Show"), tr("Make the parts of the set visible"), self.show_set), 1, 0)
        l2.addWidget(self._btn(tr("Hide"), tr("Hide the parts of the set"), self.hide_set), 1, 1)
        l2.addWidget(self._btn(tr("Isolate"), tr("Show only the set"), self.isolate_set), 1, 2)
        l2.addWidget(self._btn(tr("Isolate transp."), tr("Make everything else transparent and unselectable"), self.isolate_transparent), 2, 0)
        l2.addWidget(self._btn(tr("Show all"), tr("Make all parts visible"), self.show_all), 2, 1)
        l2.addWidget(self._btn(tr("Restore look"), tr("Undo transparency / unselectable state"), self.restore_view), 2, 2)
        lay.addWidget(g2)

        g4 = QtWidgets.QGroupBox(tr("Create"))
        l4 = QtWidgets.QGridLayout(g4)
        l4.addWidget(self._btn(tr("New part…"),
                               tr("New part file whose Body holds a SubShapeBinder of the "
                                  "current selection (faces, edges, parts), or of the set "
                                  "when nothing is selected"), self.new_part), 0, 0)
        l4.addWidget(self._btn(tr("Shape for TechDraw"),
                               tr("SubShapeBinder of the set members only (chosen faces, "
                                  "edges, parts) at the root of the document: make the "
                                  "TechDraw view of it to draw only what matters. Run it "
                                  "again after changing the set to update the same shape"),
                               self.techdraw_shape), 0, 1)
        lay.addWidget(g4)

        g3 = QtWidgets.QGroupBox(tr("Combine"))
        l3 = QtWidgets.QGridLayout(g3)
        self.comboA = QtWidgets.QComboBox()
        self.comboB = QtWidgets.QComboBox()
        l3.addWidget(QtWidgets.QLabel("A"), 0, 0)
        l3.addWidget(self.comboA, 0, 1, 1, 3)
        l3.addWidget(QtWidgets.QLabel("B"), 1, 0)
        l3.addWidget(self.comboB, 1, 1, 1, 3)
        l3.addWidget(self._btn("A ∪ B", tr("Union: new set with the parts of A and B"), lambda: self.boolean("union")), 2, 1)
        l3.addWidget(self._btn("A ∩ B", tr("Intersection: parts present in both A and B"), lambda: self.boolean("inter")), 2, 2)
        l3.addWidget(self._btn("A − B", tr("Difference: parts of A that are not in B"), lambda: self.boolean("diff")), 2, 3)
        lay.addWidget(g3)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

    # ---------- helpers ----------
    def doc(self):
        return App.ActiveDocument

    def msg(self, text):
        self.status.setText(text)

    def current_set(self, quiet=False):
        doc = self.doc()
        item = self.list.currentItem()
        if doc is None or item is None:
            if not quiet:
                self.msg(tr("Pick a set in the list first."))
            return None
        return doc.getObject(item.data(USER_ROLE))

    def need_selection(self, doc):
        keys = selection_keys(doc, self.elements.isChecked())
        if not keys:
            self.msg(tr("Nothing is selected in the 3D view or the tree."))
        return keys

    def _transaction(self, doc, name, fn):
        doc.openTransaction(name)
        try:
            return fn()
        finally:
            doc.commitTransaction()

    def _ask_name(self, title, default):
        name, ok = QtWidgets.QInputDialog.getText(self, title, tr("Set name:"), text=default)
        name = (name or "").strip()
        return name if ok and name else None

    # ---------- refresh ----------
    def _compute_signature(self):
        doc = self.doc()
        if doc is None:
            return None
        try:
            return (doc.Name, tuple((s.Name, s.Label, len(get_members(s)))
                                    for s in list_sets(doc)))
        except Exception:
            return None

    def refresh_if_changed(self):
        if not self.isVisible():
            return
        if self._compute_signature() != self._signature:
            self.refresh()

    def refresh(self, select_name=None):
        doc = self.doc()
        cur = select_name
        if cur is None and self.list.currentItem() is not None:
            cur = self.list.currentItem().data(USER_ROLE)
        a_cur = self.comboA.currentData() if self.comboA.count() else None
        b_cur = self.comboB.currentData() if self.comboB.count() else None

        self.list.clear()
        self.comboA.clear()
        self.comboB.clear()
        self._signature = self._compute_signature()
        if doc is None:
            self.msg(tr("No active document."))
            return
        for s in list_sets(doc):
            n = len(get_members(s))
            # ◆: the set holds faces / edges / vertices
            mark = "  ◆" if any(element_of(k) for k in get_members(s)) else ""
            it = QtWidgets.QListWidgetItem("%s   (%d)%s" % (s.Label, n, mark))
            it.setData(USER_ROLE, s.Name)
            self.list.addItem(it)
            if s.Name == cur:
                self.list.setCurrentItem(it)
            self.comboA.addItem(s.Label, s.Name)
            self.comboB.addItem(s.Label, s.Name)
        for combo, val in ((self.comboA, a_cur), (self.comboB, b_cur)):
            i = combo.findData(val) if val else -1
            if i >= 0:
                combo.setCurrentIndex(i)
        if self.comboB.count() > 1 and self.comboB.currentIndex() == self.comboA.currentIndex():
            self.comboB.setCurrentIndex(1 if self.comboA.currentIndex() == 0 else 0)

    # ---------- compose ----------
    def new_set(self):
        doc = self.doc()
        if doc is None:
            return
        keys = self.need_selection(doc)
        if not keys:
            return
        name = self._ask_name(tr("New set"),
                              tr("Set {n}").format(n=len(list_sets(doc)) + 1))
        if not name:
            return
        s = self._transaction(doc, tr("New selection set"),
                              lambda: create_set(doc, name, keys))
        self.refresh(s.Name)
        self.msg(tr("Set “{name}” created: {n} item(s).").format(name=name, n=len(keys)))

    def add_to_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        keys = self.need_selection(doc)
        if not keys:
            return
        before = get_members(s)
        self._transaction(doc, tr("Add to set"), lambda: set_members(s, before + keys))
        self.refresh()
        self.msg(tr("{n} item(s) added to “{name}”.").format(
            n=len(get_members(s)) - len(before), name=s.Label))

    def remove_from_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        keys = self.need_selection(doc)
        if not keys:
            return
        members = get_members(s)
        rm = set(keys)
        new = [k for k in members if k not in rm]
        if len(new) == len(members):
            # The selection may be inside a sub-assembly of the set:
            # expand the set into individual parts before removing.
            with _Busy():
                rm = set(expand(doc, keys))
                new = [k for k in expand(doc, members) if k not in rm]
        removed = len(members) - len(new)
        self._transaction(doc, tr("Remove from set"), lambda: set_members(s, new))
        self.refresh()
        if removed > 0:
            self.msg(tr("Removed from “{name}”. The set now has {n} item(s).").format(
                name=s.Label, n=len(new)))
        else:
            self.msg(tr("Set “{name}” expanded into parts; {n} item(s).").format(
                name=s.Label, n=len(new)))

    def replace_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        keys = self.need_selection(doc)
        if not keys:
            return
        self._transaction(doc, tr("Replace set"), lambda: set_members(s, keys))
        self.refresh()
        self.msg(tr("“{name}” replaced: {n} item(s).").format(name=s.Label, n=len(keys)))

    def filter_set(self):
        doc = self.doc()
        if doc is None:
            return
        dlg = FilterDialog(self)
        if not _exec(dlg):
            return
        try:
            with _Busy():
                keys = dlg.run_filter(doc)
        except re.error as e:
            self.msg(tr("Invalid regular expression: {error}").format(error=e))
            return
        if not keys:
            self.msg(tr("No part matches the filter."))
            return
        target = dlg.target.currentIndex()
        if target == 2:
            with _Busy():
                select_keys(doc, keys)
            self.msg(tr("{n} part(s) selected.").format(n=len(keys)))
        elif target == 1:
            s = self.current_set()
            if s is None:
                return
            before = get_members(s)
            self._transaction(doc, tr("Add by filter"), lambda: set_members(s, before + keys))
            self.refresh()
            self.msg(tr("{n} part(s) found, added to “{name}”.").format(n=len(keys), name=s.Label))
        else:
            default = dlg.text.text().strip() or tr("Filter")
            name = self._ask_name(tr("New set"), default)
            if not name:
                return
            s = self._transaction(doc, tr("Set by filter"), lambda: create_set(doc, name, keys))
            self.refresh(s.Name)
            self.msg(tr("Set “{name}” created: {n} part(s).").format(name=name, n=len(keys)))

    def clean_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        members = get_members(s)
        new = [k for k in members if path_objects(doc, k) is not None]
        self._transaction(doc, tr("Clean set"), lambda: set_members(s, new))
        self.refresh()
        self.msg(tr("{n} missing item(s) removed.").format(n=len(members) - len(new)))

    def rename_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        name = self._ask_name(tr("Rename"), s.Label)
        if not name:
            return
        def _do():
            s.Label = name
        self._transaction(doc, tr("Rename set"), _do)
        self.refresh()

    def duplicate_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        members = get_members(s)
        n = self._transaction(doc, tr("Duplicate set"),
                              lambda: create_set(doc, s.Label + tr(" (copy)"), members))
        self.refresh(n.Name)

    def delete_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        r = QtWidgets.QMessageBox.question(
            self, tr("Delete"),
            tr("Delete the set “{name}”?\n(the parts are not affected)").format(name=s.Label),
            MB_YES | MB_NO)
        if r != MB_YES:
            return
        label = s.Label
        self._transaction(doc, tr("Delete set"), lambda: doc.removeObject(s.Name))
        self.refresh()
        self.msg(tr("Set “{name}” deleted.").format(name=label))

    # ---------- use ----------
    def select_set(self, clear=True):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return False
        keys = get_members(s)
        with _Busy():
            missing = select_keys(doc, keys, clear=clear)
        txt = tr("“{name}”: {n} item(s) selected.").format(name=s.Label, n=len(keys) - missing)
        if missing:
            txt += " " + tr("{n} missing (Clean button).").format(n=missing)
        self.msg(txt)
        return True

    def zoom_set(self):
        if self.select_set():
            try:
                Gui.runCommand("Std_ViewFitSelection")
            except Exception:
                Gui.SendMsgToActiveView("ViewSelection")

    def _set_leaves(self, doc, s):
        with _Busy():
            return expand(doc, get_members(s))

    def show_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        leaves = self._set_leaves(doc, s)
        for k in leaves:
            show_path(doc, k)
        self.msg(tr("“{name}” shown ({n} part(s)).").format(name=s.Label, n=len(leaves)))

    def hide_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        leaves = self._set_leaves(doc, s)
        for o in self._targets(doc, leaves).values():
            try:
                o.Visibility = False
            except Exception:
                pass
        self.msg(tr("“{name}” hidden ({n} part(s)).").format(name=s.Label, n=len(leaves)))

    def isolate_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        with _Busy():
            wanted = expand(doc, get_members(s))
            keep = self._wanted_ids(doc, wanted)
            for i, o in self._targets(doc, all_leaves(doc)).items():
                if i not in keep:
                    try:
                        o.Visibility = False
                    except Exception:
                        pass
            for k in wanted:
                show_path(doc, k)
        self.msg(tr("“{name}” isolated ({n} part(s)). “Show all” to go back.").format(
            name=s.Label, n=len(wanted)))

    def _targets(self, doc, keys):
        """{id: visibility target} of members, each object once."""
        out = {}
        for k in keys:
            o = visibility_target(doc, k)
            if o is not None:
                out.setdefault(oid(o), o)
        return out

    def _wanted_ids(self, doc, wanted):
        """Ids of every object on the visibility chains of the wanted members
        (their containers must not be hidden either)."""
        ids = set()
        for k in wanted:
            ids.update(oid(o) for o in visibility_chain(doc, k))
        return ids

    def _remember_view(self, doc, o):
        vo = getattr(o, "ViewObject", None)
        if vo is None:
            return None
        key = (doc.Name, o.Name)
        if key not in self._saved_view:
            self._saved_view[key] = (getattr(vo, "Transparency", None),
                                     getattr(vo, "Selectable", None))
        return vo

    def isolate_transparent(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        with _Busy():
            wanted = expand(doc, get_members(s))
            wanted_objs = set(self._targets(doc, wanted))
            keep = self._wanted_ids(doc, wanted)
            for i, o in self._targets(doc, all_leaves(doc)).items():
                if i in keep and i not in wanted_objs:
                    continue            # container of a wanted part
                vo = self._remember_view(doc, o)
                if vo is None:
                    continue
                saved = self._saved_view.get((doc.Name, o.Name), (None, None))
                try:
                    if i in wanted_objs:
                        if saved[0] is not None and hasattr(vo, "Transparency"):
                            vo.Transparency = saved[0]
                        if hasattr(vo, "Selectable"):
                            vo.Selectable = True
                    else:
                        if hasattr(vo, "Transparency"):
                            vo.Transparency = TRANSPARENCY
                        if hasattr(vo, "Selectable"):
                            vo.Selectable = False
                except Exception:
                    pass
            for k in wanted:
                show_path(doc, k)
        self.msg(tr("“{name}” highlighted; the rest is transparent and unselectable. "
                    "“Restore look” to go back.").format(name=s.Label))

    def restore_view(self):
        doc = self.doc()
        if doc is None:
            return
        n = 0
        for (dname, oname), (transp, selectable) in list(self._saved_view.items()):
            if dname != doc.Name:
                continue
            o = doc.getObject(oname)
            vo = getattr(o, "ViewObject", None) if o is not None else None
            if vo is not None:
                try:
                    if transp is not None:
                        vo.Transparency = transp
                    if selectable is not None:
                        vo.Selectable = selectable
                    n += 1
                except Exception:
                    pass
            del self._saved_view[(dname, oname)]
        self.msg(tr("Look restored on {n} part(s).").format(n=n))

    def show_all(self):
        doc = self.doc()
        if doc is None:
            return
        with _Busy():
            leaves = all_leaves(doc)
            for k in leaves:
                show_path(doc, k)
        self.msg(tr("All parts are visible ({n}).").format(n=len(leaves)))

    # ---------- create ----------
    def techdraw_shape(self):
        """Create, or update, the SubShapeBinder of the members of the current
        set, at the root of the document (outside any assembly: no dependency
        cycle). The binder remembers its set (property SetShapeOf), so after
        adding or removing members the same binder is updated and the
        TechDraw views made from it follow."""
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        supports = []
        for k in get_members(s):
            if path_objects(doc, k) is None:
                continue
            r, sub = split_key(k)
            root = doc.getObject(r)
            for o, subs in supports:
                if o is root:
                    subs.append(sub)
                    break
            else:
                supports.append((root, [sub]))
        if not supports:
            self.msg(tr("The set is empty or its members no longer exist."))
            return
        existing = set_shape(doc, s)

        def _do():
            b = existing
            if b is None:
                b = doc.addObject("PartDesign::SubShapeBinder", "SetShape")
                b.addProperty("App::PropertyString", "SetShapeOf", "Selection set",
                              "Internal name of the selection set this shape is made from")
                b.SetShapeOf = s.Name
                b.MakeFace = False      # keep chosen edges as edges
            b.Label = tr("{name} (shape)").format(name=s.Label)
            b.Support = [(o, tuple(subs)) for o, subs in supports]
            doc.recompute()
            return b
        b = self._transaction(doc, tr("Shape of the set"), _do)
        if existing is None:
            self.msg(tr("“{name}” created: select it, then insert a TechDraw view.").format(
                name=b.Label))
        else:
            self.msg(tr("“{name}” updated with the {n} member(s) of the set.").format(
                name=b.Label, n=len(get_members(s))))
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(b)
        except Exception:
            pass

    def new_part(self):
        doc = self.doc()
        if doc is None:
            return
        from . import new_part
        keys = new_part.selection_keys(doc)
        if not keys:
            s = self.current_set(quiet=True)
            if s is None:
                self.msg(tr("Select elements in the 3D view, or pick a set in the list."))
                return
            keys = [(doc.getObject(r), sub) for r, sub in map(split_key, get_members(s))
                    if doc.getObject(r) is not None]
        try:
            new_doc = new_part.new_part_from_selection(doc, keys)
        except Exception as e:
            self.msg(str(e))
            return
        if new_doc is not None:
            self.msg(tr("New part created: {file}").format(file=new_doc.Label))

    # ---------- combine ----------
    def boolean(self, op):
        doc = self.doc()
        if doc is None or self.comboA.count() == 0:
            self.msg(tr("At least one set is needed."))
            return
        a = doc.getObject(self.comboA.currentData())
        b = doc.getObject(self.comboB.currentData())
        if a is None or b is None:
            return
        with _Busy():
            ka = expand(doc, get_members(a))
            kb = expand(doc, get_members(b))
        sb = set(kb)
        if op == "union":
            res, sym = dedupe(ka + kb), "∪"
        elif op == "inter":
            res, sym = [k for k in ka if k in sb], "∩"
        else:
            res, sym = [k for k in ka if k not in sb], "−"
        name = self._ask_name(tr("Result"), "%s %s %s" % (a.Label, sym, b.Label))
        if not name:
            return
        s = self._transaction(doc, tr("Combine sets"), lambda: create_set(doc, name, res))
        self.refresh(s.Name)
        self.msg(tr("Set “{name}” created: {n} part(s).").format(name=name, n=len(res)))


# --------------------------------------------------------------------------
#  Launch
# --------------------------------------------------------------------------
def show_panel():
    mw = Gui.getMainWindow()
    for d in mw.findChildren(QtWidgets.QDockWidget, DOCK_NAME):
        d.close()
        d.setParent(None)
        d.deleteLater()
    doc = App.ActiveDocument
    if doc is not None and prefs.get("LeaveAssemblyForSelectionSets") \
            and leave_assembly_edit(doc):
        App.Console.PrintMessage(tr("Selection sets: assembly edit mode left, faces, "
                                    "edges and vertices can be selected.") + "\n")
    dock = QtWidgets.QDockWidget(tr("Selection sets"), mw)
    dock.setObjectName(DOCK_NAME)
    panel = SelectionSetsPanel(dock)
    dock.setWidget(panel)
    mw.addDockWidget(RIGHT_AREA, dock)
    dock.show()
    Gui.JeuxDeSelectionPanel = panel  # keep a Python reference alive
    return dock
