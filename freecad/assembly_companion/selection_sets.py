# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# ---------------------------------------------------------------------------
#  selection_sets.py (Assembly Companion)
#  Docked panel to create, edit and reuse named selection sets in large
#  assemblies (STEP files exploded into hundreds of parts, old assemblies,
#  hidden parts, repeated selections while modelling).
#
#  - Sets are stored INSIDE the document ("Jeux de sélection" group), so they
#    are saved with the .FCStd file. Parts are never moved.
#  - Each member is stored by its full path (root + subpath), which tells
#    apart the different instances of the same part (App::Link).
#  - Works with FreeCAD 0.21, 1.0, 1.1 and 26.x (PySide2 or PySide6).
#
#  User-facing texts are in French; code comments are in English.
# ---------------------------------------------------------------------------

__Title__ = "Jeux de sélection"
__Author__ = "Claude"
__Version__ = "1.0"
__Comment__ = "Gestionnaire de jeux de sélection nommés pour gros assemblages"

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


def path_names(sub):
    return [n for n in (sub or "").split(".") if n]


def path_objects(doc, k):
    """Objects along the path [root, ..., leaf], or None."""
    rname, sub = split_key(k)
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
    out = []
    for k in keys:
        walk_leaves(doc, k, out)
    return dedupe(out)


def leaf_of(doc, k):
    objs = path_objects(doc, k)
    return objs[-1] if objs else None


def show_path(doc, k):
    anc = path_ancestors(doc, k)
    if not anc:
        return False
    for o in anc:
        try:
            if not o.Visibility:
                o.Visibility = True
        except Exception:
            pass
    return True


def path_is_visible(doc, k):
    anc = path_ancestors(doc, k)
    if not anc:
        return False
    try:
        return all(o.Visibility for o in anc)
    except Exception:
        return True


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
    g.addProperty("App::PropertyBool", GROUP_MARK, "Jeux de sélection",
                  "Marqueur du groupe des jeux de sélection")
    setattr(g, GROUP_MARK, True)
    g.Label = "Jeux de sélection"
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


def create_set(doc, label, keys):
    g = find_group(doc, create=True)
    s = doc.addObject("App::FeaturePython", "JeuSel")
    s.addProperty("App::PropertyStringList", PROP, "Jeu de sélection",
                  "Membres : NomRacine|sous.chemin.")
    s.Label = label
    set_members(s, keys)
    g.addObject(s)
    try:
        g.purgeTouched()
    except Exception:
        pass
    return s


def selection_keys(doc):
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
    TARGETS = ["Nouveau jeu", "Ajouter au jeu courant",
               "Sélectionner seulement"]

    def __init__(self, parent=None):
        super(FilterDialog, self).__init__(parent)
        self.setWindowTitle("Filtrer les pièces")
        form = QtWidgets.QFormLayout(self)

        self.text = QtWidgets.QLineEdit()
        self.text.setPlaceholderText("ex. vis, M6, roulement…  (vide = tout)")
        self.regex = QtWidgets.QCheckBox("Expression régulière")
        self.parents = QtWidgets.QCheckBox(
            "Chercher aussi dans les noms des sous-ensembles parents")
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
        self.visible = QtWidgets.QCheckBox("Seulement les pièces visibles")
        self.target = QtWidgets.QComboBox()
        self.target.addItems(self.TARGETS)

        form.addRow("Nom contient :", self.text)
        form.addRow("", self.regex)
        form.addRow("", self.parents)
        form.addRow("Taille min (diag. boîte) :", self.smin)
        form.addRow("Taille max (diag. boîte) :", self.smax)
        form.addRow("Volume min :", self.vmin)
        form.addRow("Volume max :", self.vmax)
        form.addRow("", self.visible)
        form.addRow("Résultat :", self.target)

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
        self.list.setToolTip("Double-clic : sélectionner le jeu")
        self.list.itemDoubleClicked.connect(lambda *_: self.select_set())
        lay.addWidget(self.list, 1)

        g1 = QtWidgets.QGroupBox("Composer")
        l1 = QtWidgets.QGridLayout(g1)
        l1.addWidget(self._btn("Nouveau", "Créer un jeu à partir de la sélection courante", self.new_set), 0, 0)
        l1.addWidget(self._btn("+ Ajouter", "Ajouter la sélection courante au jeu", self.add_to_set), 0, 1)
        l1.addWidget(self._btn("− Retirer", "Retirer la sélection courante du jeu", self.remove_from_set), 0, 2)
        l1.addWidget(self._btn("Remplacer", "Remplacer le contenu du jeu par la sélection courante", self.replace_set), 1, 0)
        l1.addWidget(self._btn("Filtre…", "Créer / compléter un jeu par nom, taille, volume", self.filter_set), 1, 1)
        l1.addWidget(self._btn("Nettoyer", "Supprimer du jeu les pièces qui n'existent plus", self.clean_set), 1, 2)
        l1.addWidget(self._btn("Renommer", "Renommer le jeu", self.rename_set), 2, 0)
        l1.addWidget(self._btn("Dupliquer", "Copier le jeu", self.duplicate_set), 2, 1)
        l1.addWidget(self._btn("Supprimer", "Supprimer le jeu (pas les pièces)", self.delete_set), 2, 2)
        lay.addWidget(g1)

        g2 = QtWidgets.QGroupBox("Utiliser")
        l2 = QtWidgets.QGridLayout(g2)
        l2.addWidget(self._btn("Sélectionner", "Remplacer la sélection par le jeu", self.select_set), 0, 0)
        l2.addWidget(self._btn("Sélect. +", "Ajouter le jeu à la sélection courante", lambda: self.select_set(clear=False)), 0, 1)
        l2.addWidget(self._btn("Zoom", "Sélectionner le jeu et cadrer la vue dessus", self.zoom_set), 0, 2)
        l2.addWidget(self._btn("Afficher", "Rendre visibles les pièces du jeu", self.show_set), 1, 0)
        l2.addWidget(self._btn("Masquer", "Masquer les pièces du jeu", self.hide_set), 1, 1)
        l2.addWidget(self._btn("Isoler", "N'afficher que le jeu", self.isolate_set), 1, 2)
        l2.addWidget(self._btn("Isoler transp.", "Rendre tout le reste transparent et non sélectionnable", self.isolate_transparent), 2, 0)
        l2.addWidget(self._btn("Tout afficher", "Rendre toutes les pièces visibles", self.show_all), 2, 1)
        l2.addWidget(self._btn("Rétablir aspect", "Annuler les transparences / non-sélectionnables", self.restore_view), 2, 2)
        lay.addWidget(g2)

        g3 = QtWidgets.QGroupBox("Combiner")
        l3 = QtWidgets.QGridLayout(g3)
        self.comboA = QtWidgets.QComboBox()
        self.comboB = QtWidgets.QComboBox()
        l3.addWidget(QtWidgets.QLabel("A"), 0, 0)
        l3.addWidget(self.comboA, 0, 1, 1, 3)
        l3.addWidget(QtWidgets.QLabel("B"), 1, 0)
        l3.addWidget(self.comboB, 1, 1, 1, 3)
        l3.addWidget(self._btn("A ∪ B", "Union : nouveau jeu avec les pièces de A et de B", lambda: self.boolean("union")), 2, 1)
        l3.addWidget(self._btn("A ∩ B", "Intersection : pièces présentes dans A et dans B", lambda: self.boolean("inter")), 2, 2)
        l3.addWidget(self._btn("A − B", "Différence : pièces de A qui ne sont pas dans B", lambda: self.boolean("diff")), 2, 3)
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
                self.msg("Choisis d'abord un jeu dans la liste.")
            return None
        return doc.getObject(item.data(USER_ROLE))

    def need_selection(self, doc):
        keys = selection_keys(doc)
        if not keys:
            self.msg("Rien n'est sélectionné dans la vue 3D ou l'arbre.")
        return keys

    def _transaction(self, doc, name, fn):
        doc.openTransaction(name)
        try:
            return fn()
        finally:
            doc.commitTransaction()

    def _ask_name(self, title, default):
        name, ok = QtWidgets.QInputDialog.getText(self, title, "Nom du jeu :", text=default)
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
            self.msg("Aucun document actif.")
            return
        for s in list_sets(doc):
            n = len(get_members(s))
            it = QtWidgets.QListWidgetItem("%s   (%d)" % (s.Label, n))
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
        name = self._ask_name("Nouveau jeu", "Jeu %d" % (len(list_sets(doc)) + 1))
        if not name:
            return
        s = self._transaction(doc, "Nouveau jeu de sélection",
                              lambda: create_set(doc, name, keys))
        self.refresh(s.Name)
        self.msg("Jeu « %s » créé : %d élément(s)." % (name, len(keys)))

    def add_to_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        keys = self.need_selection(doc)
        if not keys:
            return
        before = get_members(s)
        self._transaction(doc, "Ajouter au jeu", lambda: set_members(s, before + keys))
        self.refresh()
        self.msg("%d élément(s) ajouté(s) à « %s »." % (len(get_members(s)) - len(before), s.Label))

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
        self._transaction(doc, "Retirer du jeu", lambda: set_members(s, new))
        self.refresh()
        if removed > 0:
            self.msg("Retiré de « %s ». Le jeu compte maintenant %d élément(s)." % (s.Label, len(new)))
        else:
            self.msg("Jeu « %s » détaillé en pièces ; %d élément(s)." % (s.Label, len(new)))

    def replace_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        keys = self.need_selection(doc)
        if not keys:
            return
        self._transaction(doc, "Remplacer le jeu", lambda: set_members(s, keys))
        self.refresh()
        self.msg("« %s » remplacé : %d élément(s)." % (s.Label, len(keys)))

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
            self.msg("Expression régulière invalide : %s" % e)
            return
        if not keys:
            self.msg("Aucune pièce ne correspond au filtre.")
            return
        target = dlg.target.currentIndex()
        if target == 2:
            with _Busy():
                select_keys(doc, keys)
            self.msg("%d pièce(s) sélectionnée(s)." % len(keys))
        elif target == 1:
            s = self.current_set()
            if s is None:
                return
            before = get_members(s)
            self._transaction(doc, "Ajouter par filtre", lambda: set_members(s, before + keys))
            self.refresh()
            self.msg("%d pièce(s) trouvée(s), ajoutée(s) à « %s »." % (len(keys), s.Label))
        else:
            default = dlg.text.text().strip() or "Filtre"
            name = self._ask_name("Nouveau jeu", default)
            if not name:
                return
            s = self._transaction(doc, "Jeu par filtre", lambda: create_set(doc, name, keys))
            self.refresh(s.Name)
            self.msg("Jeu « %s » créé : %d pièce(s)." % (name, len(keys)))

    def clean_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        members = get_members(s)
        new = [k for k in members if path_objects(doc, k) is not None]
        self._transaction(doc, "Nettoyer le jeu", lambda: set_members(s, new))
        self.refresh()
        self.msg("%d élément(s) introuvable(s) retiré(s)." % (len(members) - len(new)))

    def rename_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        name = self._ask_name("Renommer", s.Label)
        if not name:
            return
        def _do():
            s.Label = name
        self._transaction(doc, "Renommer le jeu", _do)
        self.refresh()

    def duplicate_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        members = get_members(s)
        n = self._transaction(doc, "Dupliquer le jeu",
                              lambda: create_set(doc, s.Label + " (copie)", members))
        self.refresh(n.Name)

    def delete_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        r = QtWidgets.QMessageBox.question(
            self, "Supprimer", "Supprimer le jeu « %s » ?\n(les pièces ne sont pas touchées)" % s.Label,
            MB_YES | MB_NO)
        if r != MB_YES:
            return
        label = s.Label
        self._transaction(doc, "Supprimer le jeu", lambda: doc.removeObject(s.Name))
        self.refresh()
        self.msg("Jeu « %s » supprimé." % label)

    # ---------- use ----------
    def select_set(self, clear=True):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return False
        keys = get_members(s)
        with _Busy():
            missing = select_keys(doc, keys, clear=clear)
        txt = "« %s » : %d élément(s) sélectionné(s)." % (s.Label, len(keys) - missing)
        if missing:
            txt += " %d introuvable(s) (bouton Nettoyer)." % missing
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
        self.msg("« %s » affiché (%d pièce(s))." % (s.Label, len(leaves)))

    def hide_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        leaves = self._set_leaves(doc, s)
        for k in leaves:
            o = leaf_of(doc, k)
            if o is not None:
                o.Visibility = False
        self.msg("« %s » masqué (%d pièce(s))." % (s.Label, len(leaves)))

    def isolate_set(self):
        doc, s = self.doc(), self.current_set()
        if s is None:
            return
        with _Busy():
            wanted = expand(doc, get_members(s))
            wanted_set = set(wanted)
            wanted_objs = set()
            for k in wanted:
                o = leaf_of(doc, k)
                if o is not None:
                    wanted_objs.add(o.Name)
            for k in all_leaves(doc):
                if k in wanted_set:
                    continue
                o = leaf_of(doc, k)
                if o is not None and o.Name not in wanted_objs:
                    o.Visibility = False
            for k in wanted:
                show_path(doc, k)
        self.msg("« %s » isolé (%d pièce(s)). « Tout afficher » pour revenir." % (s.Label, len(wanted)))

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
            wanted_objs = set()
            for k in wanted:
                o = leaf_of(doc, k)
                if o is not None:
                    wanted_objs.add(o.Name)
            for k in all_leaves(doc):
                o = leaf_of(doc, k)
                if o is None:
                    continue
                vo = self._remember_view(doc, o)
                if vo is None:
                    continue
                saved = self._saved_view.get((doc.Name, o.Name), (None, None))
                try:
                    if o.Name in wanted_objs:
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
        self.msg("« %s » mis en avant ; le reste est transparent et non sélectionnable. "
                 "« Rétablir aspect » pour revenir." % s.Label)

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
        self.msg("Aspect rétabli sur %d pièce(s)." % n)

    def show_all(self):
        doc = self.doc()
        if doc is None:
            return
        with _Busy():
            leaves = all_leaves(doc)
            for k in leaves:
                show_path(doc, k)
        self.msg("Toutes les pièces sont visibles (%d)." % len(leaves))

    # ---------- combine ----------
    def boolean(self, op):
        doc = self.doc()
        if doc is None or self.comboA.count() == 0:
            self.msg("Il faut au moins un jeu.")
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
        name = self._ask_name("Résultat", "%s %s %s" % (a.Label, sym, b.Label))
        if not name:
            return
        s = self._transaction(doc, "Combiner des jeux", lambda: create_set(doc, name, res))
        self.refresh(s.Name)
        self.msg("Jeu « %s » créé : %d pièce(s)." % (name, len(res)))


# --------------------------------------------------------------------------
#  Launch
# --------------------------------------------------------------------------
def show_panel():
    mw = Gui.getMainWindow()
    for d in mw.findChildren(QtWidgets.QDockWidget, DOCK_NAME):
        d.close()
        d.setParent(None)
        d.deleteLater()
    dock = QtWidgets.QDockWidget("Jeux de sélection", mw)
    dock.setObjectName(DOCK_NAME)
    panel = SelectionSetsPanel(dock)
    dock.setWidget(panel)
    mw.addDockWidget(RIGHT_AREA, dock)
    dock.show()
    Gui.JeuxDeSelectionPanel = panel  # keep a Python reference alive
    return dock
