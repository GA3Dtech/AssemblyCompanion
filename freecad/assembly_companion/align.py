# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
align.py (Assembly Companion) - quick placement of bodies inside a
Std_Part container (static assemblies).

Workflow:
  1. Click an element (face / edge / vertex) on the object to move -> ORIGIN
  2. Click an element on another object                           -> TARGET
  3. The object is aligned at once (live preview), then adjusted in the task
     panel: object to move (Body or parent container), flip, translation only,
     X/Y/Z offset and rotations expressed in the target frame.
  Optional gizmo (checkbox): dragging it updates the fields, typing a value
  moves the gizmo.
  OK = validate (single undo step), Cancel = back to the initial state.

Frame taken on each element:
  - planar face           : center of mass, Z = outward normal
  - cylinder / cone / sphere : point on the axis, Z = axis
  - circular edge         : center, Z = circle axis
  - straight edge         : midpoint, Z = direction
  - vertex                : point, no orientation (translation only)
By default the Z axes are opposed (faces in contact); "Flip" makes them
point the same way.

User-facing texts are in English, translated through i18n.tr().

v1.0 - first consolidated version (tested on FreeCAD 26.3rc2).
       History: full selection path recovered from the root (FreeCAD may pass
       only the deepest object, e.g. 'Pad'); in an assembly the Link is moved,
       not its target; optional gizmo polled by timer.
"""

import FreeCAD as App
import FreeCADGui as Gui
import Part

try:
    from PySide import QtWidgets, QtCore
except ImportError:
    from PySide import QtGui as QtWidgets, QtCore

from .i18n import tr

V = App.Vector

# 'auto' = FreeCAD's own dragger (the Transform tool one) when available,
# 'coin' = generic Coin dragger (box), plainer but always available.
DRAGGER = 'auto'
# True = print every movement read on the gizmo in the report view
DEBUG_GIZMO = False
# True = trace every step (clicks, frames, placement) in the report view
TRACE = False


def trace(msg):
    if TRACE:
        App.Console.PrintMessage("[Align] " + msg + "\n")



# --------------------------------------------------------------------------
#  Geometry
# --------------------------------------------------------------------------

def _x_perp(z):
    """An X axis perpendicular to z, stable (projection of global X, else Y)."""
    for ref in (V(1, 0, 0), V(0, 1, 0)):
        x = ref - z * ref.dot(z)
        if x.Length > 1e-6:
            return x.normalize()
    return V(1, 0, 0)


def _repere(origine, z=None, x=None):
    """Return (Placement, oriented). No z -> position only, not oriented."""
    if z is None or z.Length < 1e-9:
        return App.Placement(origine, App.Rotation()), False
    z = V(z).normalize()
    if x is None or abs(V(x).normalize().dot(z)) > 0.999:
        x = _x_perp(z)
    else:
        x = V(x)
        x = (x - z * x.dot(z)).normalize()
    y = z.cross(x)
    return App.Placement(origine, App.Rotation(x, y, z, 'ZXY')), True


def _centre(g):
    """Center of a conic / surface of revolution, without touching the
    deprecated 'Center' attribute when 'Location' exists (FreeCAD 26.3+)."""
    if hasattr(g, 'Location'):
        return g.Location
    if hasattr(g, 'Center'):
        return g.Center
    return None


def repere_element(el):
    """Local frame (Placement, oriented) of a face / edge / vertex, in global
    coordinates."""
    t = el.ShapeType
    if t == 'Vertex':
        return _repere(el.Point)
    if t == 'Edge':
        c = el.Curve
        if hasattr(c, 'Axis') and _centre(c) is not None:   # circle, ellipse
            return _repere(_centre(c), c.Axis)
        if isinstance(c, (Part.Line, Part.LineSegment)) or 'Line' in type(c).__name__:
            p0, p1 = el.Vertexes[0].Point, el.Vertexes[-1].Point
            return _repere((p0 + p1) * 0.5, p1 - p0)
        return _repere(el.CenterOfMass)
    if t == 'Face':
        s = el.Surface
        com = el.CenterOfMass
        if isinstance(s, Part.Plane) or 'Plane' in type(s).__name__:
            u, v = s.parameter(com)
            n = el.normalAt(u, v)
            xdir = None
            for e in el.Edges:                       # X along a straight edge
                if 'Line' in type(e.Curve).__name__:
                    xdir = e.Vertexes[-1].Point - e.Vertexes[0].Point
                    break
            return _repere(com, n, xdir)
        if hasattr(s, 'Axis') and _centre(s) is not None:   # cylinder, cone, sphere, torus
            a = V(s.Axis).normalize()
            c = _centre(s)
            return _repere(c + a * (com - c).dot(a), a)
        try:
            u, v = s.parameter(com)
            return _repere(com, el.normalAt(u, v))
        except Exception:
            return _repere(com)
    return _repere(el.CenterOfMass if hasattr(el, 'CenterOfMass') else V())


def placement_chaine(chaine, idx):
    """Global placement of chaine[idx] (chaine = [top, ..., object])."""
    pl = App.Placement()
    for i, o in enumerate(chaine[:idx + 1]):
        if i > 0 and chaine[i - 1].isDerivedFrom('App::Link') and \
                not getattr(chaine[i - 1], 'LinkTransform', False):
            continue                       # target placement is ignored by the Link
        if hasattr(o, 'Placement'):
            pl = pl.multiply(o.Placement)
    return pl


def candidats_mobiles(chaine):
    """Indices of the movable objects in the chain (not the features of a Body)."""
    res = []
    for i, o in enumerate(chaine):
        if not hasattr(o, 'Placement'):
            continue
        if i > 0 and chaine[i - 1].isDerivedFrom('PartDesign::Body'):
            continue
        if i > 0 and chaine[i - 1].isDerivedFrom('App::Link') and \
                not getattr(chaine[i - 1], 'LinkTransform', False):
            continue      # Link target: its placement is ignored, the Link is moved instead
        if o.isDerivedFrom('PartDesign::Feature') or o.isDerivedFrom('App::Origin') \
                or o.isDerivedFrom('App::OriginFeature') or o.isDerivedFrom('Sketcher::SketchObject'):
            continue
        res.append(i)
    return res


class Pick(object):
    """A clicked element: root object, subname, object chain, global frame."""

    def __init__(self, doc_name, obj_name, sub):
        doc = App.getDocument(doc_name)
        self.top = doc.getObject(obj_name)
        self.sub = sub
        chemin = sub[:sub.rfind('.') + 1] if '.' in sub else ''
        self.chaine = self.top.getSubObjectList(chemin) if chemin else [self.top]
        el = Part.getShape(self.top, sub, needSubElement=True)
        if el.isNull():
            raise ValueError(tr("empty element"))
        self.repere, self.oriente = repere_element(el)
        self.texte = '%s  [%s]' % (self.chaine[-1].Label if self.chaine else self.top.Label,
                                   sub.split('.')[-1])


# --------------------------------------------------------------------------
#  Gizmo (Coin3D dragger) - polled by a timer, synchronized with the panel
# --------------------------------------------------------------------------

def _lire_vec(f):
    """Read an SoSFVec3f field (typed access, else string fallback)."""
    try:
        return tuple(float(x) for x in f.getValue().getValue())
    except Exception:
        return tuple(float(x) for x in f.get().split()[:3])


def _lire_rot(f):
    """Read an SoSFRotation field as an App.Rotation."""
    try:
        q = f.getValue().getValue()                  # quaternion (x, y, z, w)
        return App.Rotation(*[float(x) for x in q])
    except Exception:
        r = [float(x) for x in f.get().split()]      # axis x y z + angle (rad)
        if V(r[0], r[1], r[2]).Length < 1e-12:
            return App.Rotation()
        return App.Rotation(V(r[0], r[1], r[2]), r[3] * 180.0 / 3.141592653589793)


class Gizmo(object):
    """Dragger placed in the base frame (target * flip); its translation and
    rotation are the panel offset. Movement is detected by reading the dragger
    fields every 40 ms (Coin sensors called from Python proved unreliable)."""

    def __init__(self, vue, taille, on_move):
        from pivy import coin
        self.coin = coin
        self.vue = vue
        self.on_move = on_move
        self.sep = coin.SoSeparator()
        self.xf = coin.SoTransform()
        self.sep.addChild(self.xf)
        self.drag = None
        self.nom = 'SoTransformerDragger'
        if DRAGGER == 'auto':
            # class name depends on the FreeCAD version
            for nom in ('SoTransformDragger', 'SoFCCSysDragger'):
                try:
                    t = coin.SoType.fromName(nom)
                    if not t.isBad():
                        self.drag = t.createInstance()
                        self.nom = nom
                        break
                except Exception:
                    pass
        if self.drag is None:
            self.drag = coin.SoTransformerDragger()
            self.nom = 'SoTransformerDragger'
        self.sep.addChild(self.drag)
        self._regler_taille(taille)
        self.f_trans = self.drag.getField('translation')
        self.f_rot = self.drag.getField('rotation')
        self.dernier = None
        self.erreur_signalee = False
        vue.getSceneGraph().addChild(self.sep)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._surveiller)
        self.timer.start(40)
        App.Console.PrintMessage("Align: gizmo = %s, size = %.1f mm\n" % (self.nom, taille))

    def _regler_taille(self, taille):
        # FreeCAD's dragger normally auto-scales with the camera (not reachable
        # from Python): without it it stays at scale 1 (~1 mm). Force the size.
        if self.nom == 'SoTransformerDragger':
            reglages = [('scaleFactor', '%g %g %g' % (taille / 2, taille / 2, taille / 2))]
        else:
            reglages = [('autoScaleResult', '%g' % (taille / 8.0))]
        for nom, val in reglages:
            try:
                f = self.drag.getField(nom)
                if f is not None:
                    f.set(val)
            except Exception as e:
                App.Console.PrintWarning("Align: cannot set %s (%s)\n" % (nom, e))

    def _etat(self):
        t = _lire_vec(self.f_trans)
        r = _lire_rot(self.f_rot)
        return t, r

    def set_base(self, pl):
        self.xf.translation.setValue(pl.Base.x, pl.Base.y, pl.Base.z)
        q = pl.Rotation.Q
        self.xf.rotation.setValue(q[0], q[1], q[2], q[3])

    def set_offset(self, pl):
        self.f_trans.set('%.9g %.9g %.9g' % (pl.Base.x, pl.Base.y, pl.Base.z))
        a = pl.Rotation.Axis
        self.f_rot.set('%.9g %.9g %.9g %.9g' % (a.x, a.y, a.z, pl.Rotation.Angle))
        try:
            self.dernier = self._etat()          # avoid a false "movement"
        except Exception:
            self.dernier = None

    def _surveiller(self):
        try:
            t, r = self._etat()
        except Exception as e:
            if not self.erreur_signalee:
                App.Console.PrintError("Align: cannot read the gizmo (%s)\n" % e)
                self.erreur_signalee = True
            return
        if self.dernier is not None:
            t0, r0 = self.dernier
            if (V(*t) - V(*t0)).Length < 1e-7 and \
                    abs(r.multiply(r0.inverted()).Angle) < 1e-9:
                return
        self.dernier = (t, r)
        if DEBUG_GIZMO:
            App.Console.PrintMessage("Align: gizmo read  T=%s  R=%s\n" % (t, r.toEuler()))
        try:
            self.on_move(App.Placement(V(*t), r))
        except Exception as e:
            import traceback
            App.Console.PrintError(tr("Align: gizmo stopped ({error})").format(error=e)
                                   + "\n%s\n" % traceback.format_exc())
            self.timer.stop()

    def retirer(self):
        self.timer.stop()
        try:
            self.vue.getSceneGraph().removeChild(self.sep)
        except Exception:
            pass


# --------------------------------------------------------------------------
#  Task panel
# --------------------------------------------------------------------------

class PanneauAligner(object):

    def __init__(self):
        self.doc = App.ActiveDocument
        self.origine = None
        self.cible = None
        self.mobile = None          # moved object
        self.idx_mobile = None
        self.pl_initiales = {}      # object -> initial Placement
        self.etape = 'origine'
        self.gizmo = None
        self.doc.openTransaction(tr("Align elements"))
        self._construire_ui()
        Gui.Selection.clearSelection()
        try:
            Gui.Selection.addObserver(self, 0)    # 0 = full path, Links not resolved
        except TypeError:
            Gui.Selection.addObserver(self)
        trace("selection observer installed")

    # ---- UI ---------------------------------------------------------------
    def _spin(self, mini, maxi, pas, suffixe, dec=3):
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(mini, maxi)
        s.setSingleStep(pas)
        s.setDecimals(dec)
        s.setSuffix(suffixe)
        s.setKeyboardTracking(False)
        s.valueChanged.connect(self.appliquer)
        return s

    def _construire_ui(self):
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(tr("Align elements"))
        lay = QtWidgets.QVBoxLayout(self.form)

        self.lbl_etat = QtWidgets.QLabel()
        self.lbl_etat.setWordWrap(True)
        lay.addWidget(self.lbl_etat)

        g = QtWidgets.QFormLayout()
        self.lbl_orig = QtWidgets.QLabel('—')
        self.lbl_cible = QtWidgets.QLabel('—')
        b_o = QtWidgets.QPushButton(tr("Pick origin again"))
        b_c = QtWidgets.QPushButton(tr("Pick target again"))
        b_o.clicked.connect(lambda: self._passer('origine'))
        b_c.clicked.connect(lambda: self._passer('cible'))
        g.addRow(tr("Origin:"), self.lbl_orig)
        g.addRow("", b_o)
        g.addRow(tr("Target:"), self.lbl_cible)
        g.addRow("", b_c)
        self.cb_mobile = QtWidgets.QComboBox()
        self.cb_mobile.currentIndexChanged.connect(self._changer_mobile)
        g.addRow(tr("Moved object:"), self.cb_mobile)
        lay.addLayout(g)

        self.ck_inv = QtWidgets.QCheckBox(tr("Flip (Z in the same direction)"))
        self.ck_trans = QtWidgets.QCheckBox(tr("Translation only (keep orientation)"))
        for ck in (self.ck_inv, self.ck_trans):
            ck.toggled.connect(self.appliquer)
            lay.addWidget(ck)
        self.ck_gizmo = QtWidgets.QCheckBox(tr("Show gizmo (experimental)"))
        self.ck_gizmo.setChecked(False)
        self.ck_gizmo.toggled.connect(self._basculer_gizmo)
        lay.addWidget(self.ck_gizmo)

        g2 = QtWidgets.QFormLayout()
        self.dx = self._spin(-1e6, 1e6, 1.0, ' mm')
        self.dy = self._spin(-1e6, 1e6, 1.0, ' mm')
        self.dz = self._spin(-1e6, 1e6, 1.0, ' mm')
        self.rz = self._spin(-360, 360, 15.0, ' °', 2)
        self.rx = self._spin(-360, 360, 15.0, ' °', 2)
        self.ry = self._spin(-360, 360, 15.0, ' °', 2)
        g2.addRow(tr("Offset X:"), self.dx)
        g2.addRow(tr("Offset Y:"), self.dy)
        g2.addRow(tr("Offset Z:"), self.dz)
        hz = QtWidgets.QHBoxLayout()
        hz.addWidget(self.rz)
        b90 = QtWidgets.QPushButton("+90°")
        b90.clicked.connect(lambda: self.rz.setValue(((self.rz.value() + 90 + 180) % 360) - 180))
        hz.addWidget(b90)
        g2.addRow(tr("Rotation Z:"), hz)
        g2.addRow(tr("Rotation X:"), self.rx)
        g2.addRow(tr("Rotation Y:"), self.ry)
        lay.addLayout(g2)
        b_raz = QtWidgets.QPushButton(tr("Reset offsets"))
        b_raz.clicked.connect(self._raz)
        lay.addWidget(b_raz)
        lay.addStretch()
        self._maj_etat()

    def _maj_etat(self, msg=None):
        if msg:
            self.lbl_etat.setText(msg)
        elif self.etape == 'origine':
            self.lbl_etat.setText(tr("<b>1.</b> Click the ORIGIN element on the object to move."))
        elif self.etape == 'cible':
            self.lbl_etat.setText(tr("<b>2.</b> Click the TARGET element on another object."))
        else:
            self.lbl_etat.setText(tr("Aligned. Adjust, then OK (or pick an element again)."))

    def _raz(self):
        for s in (self.dx, self.dy, self.dz, self.rx, self.ry, self.rz):
            s.blockSignals(True)
            s.setValue(0)
            s.blockSignals(False)
        self.appliquer()

    def _passer(self, etape):
        self.etape = etape
        Gui.Selection.clearSelection()
        self._maj_etat()

    # ---- Selection observer -------------------------------------------
    def addSelection(self, doc, obj, sub, pnt):
        trace("click received: doc=%s obj=%s sub='%s' (step %s)" % (doc, obj, sub, self.etape))
        obj, sub = self._chemin_complet(doc, obj, sub)
        trace("  full path: obj=%s sub='%s'" % (obj, sub))
        if self.etape not in ('origine', 'cible'):
            return
        if not sub:
            self._maj_etat(tr("Click a FACE, an EDGE or a VERTEX in the 3D view "
                              "(not a whole object in the tree)."))
            trace("ignored: no element (whole object selected)")
            return
        try:
            p = Pick(doc, obj, sub)
        except Exception as e:
            import traceback
            trace("unusable element: %s\n%s" % (e, traceback.format_exc()))
            self._maj_etat(tr("Unusable element ({error}), click another one.").format(error=e))
            return
        trace("  chain = %s | frame = %s | oriented = %s"
              % (' > '.join(o.Label for o in p.chaine), p.repere, p.oriente))
        if self.etape == 'origine':
            self._restaurer()
            self.origine = p
            self.lbl_orig.setText(p.texte)
            self._remplir_mobiles()
            self.etape = 'cible' if self.cible is None else 'fait'
        else:
            if self.mobile is not None and self.mobile in p.chaine:
                trace("target rejected: it is on the moved object %s" % self.mobile.Label)
                self._maj_etat(tr("The target is on the moved object: choose another object."))
                return
            self.cible = p
            self.lbl_cible.setText(p.texte)
            self.etape = 'fait'
        self._maj_etat()
        QtCore.QTimer.singleShot(0, Gui.Selection.clearSelection)
        self.appliquer()

    def _chemin_complet(self, doc, obj, sub):
        """Some FreeCAD versions pass only the deepest object (e.g. 'Pad' +
        'Edge10'): recover the path from the root (e.g. 'Part' +
        'Body.Pad.Edge10') through the unresolved selection."""
        try:
            for sel in Gui.Selection.getSelectionEx(doc, 0):
                for s in sel.SubElementNames:
                    if s == sub or s.endswith('.' + sub) and \
                            (obj == sel.ObjectName or ('.' + obj + '.') in ('.' + s)):
                        return sel.ObjectName, s
        except Exception as e:
            trace("  full path not found (%s)" % e)
        return obj, sub

    # ---- Moved object -----------------------------------------------------
    def _remplir_mobiles(self):
        ch = self.origine.chaine
        self.cands = candidats_mobiles(ch)
        trace("  movable objects: %s" % [ch[i].Label for i in self.cands])
        if not self.cands:
            self._maj_etat(tr("No movable object found for this element."))
        self.cb_mobile.blockSignals(True)
        self.cb_mobile.clear()
        for i in self.cands:
            self.cb_mobile.addItem('%s  (%s)' % (ch[i].Label, ch[i].TypeId.split('::')[-1]))
        self.cb_mobile.setCurrentIndex(len(self.cands) - 1)   # deepest one (Body)
        self.cb_mobile.blockSignals(False)
        self._changer_mobile()

    def _changer_mobile(self, *_):
        if not self.origine or not self.cands:
            return
        self._restaurer()
        self.idx_mobile = self.cands[max(0, self.cb_mobile.currentIndex())]
        self.mobile = self.origine.chaine[self.idx_mobile]
        self.pl_initiales.setdefault(self.mobile, App.Placement(self.mobile.Placement))
        ch = self.origine.chaine
        self.pl_parent = placement_chaine(ch, self.idx_mobile - 1) if self.idx_mobile > 0 \
            else App.Placement()
        pl_obj_global = self.pl_parent.multiply(self.pl_initiales[self.mobile])
        # origin frame expressed in the local frame of the moved object
        self.local_orig = pl_obj_global.inverse().multiply(self.origine.repere)
        if any(o.isDerivedFrom('Assembly::AssemblyObject') for o in ch[:self.idx_mobile]):
            self._maj_etat(tr("Warning: part inside an Assembly. If it has joints "
                              "or is grounded, the solver will move it back."))
        self.appliquer()

    def _restaurer(self):
        for o, pl in self.pl_initiales.items():
            o.Placement = pl
        self.pl_initiales = {}

    # ---- Computation ------------------------------------------------------------
    def appliquer(self, *_, depuis_gizmo=False):
        if not (self.origine and self.cible and self.mobile):
            trace("apply: waiting (origin=%s target=%s moved=%s)"
                  % (bool(self.origine), bool(self.cible),
                     self.mobile.Label if self.mobile else None))
            return
        off_v = V(self.dx.value(), self.dy.value(), self.dz.value())
        pl0 = self.pl_initiales[self.mobile]
        ft = self.cible.repere
        oriente = self.origine.oriente and self.cible.oriente
        if self.ck_trans.isChecked() or not oriente:
            base = ft if self.cible.oriente else App.Placement(ft.Base, App.Rotation())
            off = App.Placement(off_v, App.Rotation())
            delta = ft.Base - self.origine.repere.Base + base.Rotation.multVec(off_v)
            glob = App.Placement(delta, App.Rotation()).multiply(self.pl_parent.multiply(pl0))
        else:
            flip = App.Placement() if self.ck_inv.isChecked() else \
                App.Placement(V(), App.Rotation(V(1, 0, 0), 180))
            base = ft.multiply(flip)
            off = App.Placement(off_v, App.Rotation(self.rz.value(), self.ry.value(),
                                                    self.rx.value()))
            # Object' such that: Object' * local_orig = Target * Flip * Offset
            glob = base.multiply(off).multiply(self.local_orig.inverse())
        avant = App.Placement(self.mobile.Placement)
        self.mobile.Placement = self.pl_parent.inverse().multiply(glob)
        trace("apply: %s  %s  ->  %s" % (self.mobile.Label, avant, self.mobile.Placement))
        self._maj_gizmo(base, off, depuis_gizmo)
        self.doc.recompute()

    # ---- Gizmo -------------------------------------------------------------
    def _basculer_gizmo(self, actif):
        if not actif and self.gizmo:
            self.gizmo.retirer()
        self.gizmo = None          # recreated on next appliquer() if checked
        self.appliquer()

    def _maj_gizmo(self, base, off, depuis_gizmo):
        if self.gizmo is False or not self.ck_gizmo.isChecked():
            return
        try:
            if self.gizmo is None:
                try:
                    taille = max(5.0, Part.getShape(self.mobile).BoundBox.DiagonalLength * 0.3)
                except Exception:
                    taille = 20.0
                self.gizmo = Gizmo(Gui.ActiveDocument.ActiveView, taille, self._gizmo_bouge)
            self.gizmo.set_base(base)
            if not depuis_gizmo:
                self.gizmo.set_offset(off)
        except Exception as e:
            import traceback
            App.Console.PrintError(tr("Align: gizmo unavailable ({error})").format(error=e)
                                   + "\n%s\n" % traceback.format_exc())
            self.gizmo = False

    def _gizmo_bouge(self, pl):
        """The gizmo was dragged: copy into the fields, then apply."""
        valeurs = [(self.dx, pl.Base.x), (self.dy, pl.Base.y), (self.dz, pl.Base.z)]
        if not self.ck_trans.isChecked():
            yaw, pitch, roll = pl.Rotation.toEuler()
            valeurs += [(self.rz, yaw), (self.ry, pitch), (self.rx, roll)]
        for sp, v in valeurs:
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self.appliquer(depuis_gizmo=True)

    # ---- End ---------------------------------------------------------------
    def _fermer(self):
        if self.gizmo:
            self.gizmo.retirer()
            self.gizmo = None
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        Gui.Control.closeDialog()

    def accept(self):
        self.doc.commitTransaction()
        self._fermer()
        return True

    def reject(self):
        self._restaurer()
        self.doc.abortTransaction()
        self.doc.recompute()
        self._fermer()
        return True

    def getStandardButtons(self):
        b = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        try:
            return int(b)
        except TypeError:          # PySide6: enums not convertible to int
            return b.value


def show():
    """Open the alignment task panel (entry point of the command)."""
    if App.ActiveDocument is None:
        App.Console.PrintError(tr("Align: no active document.") + "\n")
    elif Gui.Control.activeDialog():
        App.Console.PrintError(tr("Align: close the current task panel first.") + "\n")
    else:
        Gui.Control.showDialog(PanneauAligner())
