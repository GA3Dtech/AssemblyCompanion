# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - lightweight components for very large assemblies
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
lightweight.py (Assembly Companion) - replace components of a very large
assembly by lightweight ones, and back.

Reopening an assembly costs about 0.07 s per BREP part and 0.003 s per mesh
part (docs/benchmark.md): beyond a few hundred parts, BREP is what makes
FreeCAD crawl. A lightweight component is a Std_Part "LW_<name>" (in the
group "Lightweight components") holding:
  * Skeleton: a Part::Feature with ONLY the faces / edges / vertices used by
    the joints of the component - the joints are rewritten onto it, so the
    Assembly solver keeps working;
  * Skin: a Mesh::Feature of the whole component, decimated, for display
    (a native object: displayed by any FreeCAD, even without this addon).
    With the addon, a skin carrying LodPixels is drawn as its bounding box
    when it is small on screen (attach_lod, see below).
The Link of the component is pointed to that container (shapes are taken in
the Link's own coordinates, so the component does not move). Instances of
the same part share one lightweight component; its skeleton holds the
elements used by all of them.

The heavy original must NOT stay referenced, or FreeCAD would load its BREP
anyway and nothing would be gained: the container only keeps TEXT references
to the source (LWFile / LWObject / LWLabel, LWWasFrozen) and the element
mapping in source names (LWMap: "subname in the source object|skeleton
element"); frozen copies no longer used are deleted. "Restore full
component" opens the source file in the background, points the Link and its
joints back to the source object, and freezes it again if it was frozen.
"Open source" opens the real file to work on it.

User-facing texts are in English, translated through i18n.tr().
"""

import os

import FreeCAD as App

from . import freeze
from .i18n import tr

GROUP = "Lightweight_components"
LINEAR = 0.003               # x bounding box diagonal
ANGULAR = 0.4                # rad: round holes keep few facets
# (Mesh.decimate was tried: it leaves badly shaded slivers; a coarser
#  tessellation gives a cleaner skin for the same weight)


def is_lightweight(o):
    return o is not None and o.isDerivedFrom("App::Part") and "LWMap" in o.PropertiesList


def _is_skin(o):
    return o.isDerivedFrom("Mesh::Feature") or "LodPixels" in o.PropertiesList


def _children(cont):
    """(skeleton, [skins]) of a lightweight container."""
    sk, skins = None, []
    for c in cont.Group:
        if _is_skin(c):
            skins.append(c)
        elif c.isDerivedFrom("Part::Feature"):
            sk = c
    return sk, skins


def _group(doc):
    g = doc.getObject(GROUP)
    if g is None:
        g = doc.addObject("App::DocumentObjectGroup", GROUP)
        g.Label = tr("Lightweight components")
    return g


def _source(target, doc):
    """(file, object name, label) of the part a Link shows."""
    if freeze._est_fige(target):
        return (freeze.chemin_source(target, doc) or target.FigeFichier,
                target.FigeObjet, target.FigeLabel or target.Label)
    return target.Document.FileName, target.Name, target.Label


def _source_inner(inner, doc):
    """Subname inside a frozen container written with the source names
    ("Fige_Body001.Edge116" -> "Body001.Edge116"); unchanged otherwise."""
    objets, _mapped, elem = freeze.decouper_sub(inner)
    names = []
    for n in objets:
        o = doc.getObject(n)
        names.append(o.FigeObjet if o is not None and "FigeObjet" in o.PropertiesList else n)
    return ".".join(names) + ("." if names else "") + elem


def _element_refs(link):
    """[(ref tuple, inner subname)] of the joint references going through
    `link`; inner subname = path inside the Link + element ("Fige_Body001.Edge116")."""
    out = []
    for o, p, t, i, j, k, sub in freeze.references_via(link):
        objets, _mapped, elem = freeze.decouper_sub(sub)
        inner = objets[k + 1:]
        inner_sub = ".".join(inner) + ("." if inner else "") + elem
        out.append(((o, p, t, i, j, k, sub), inner_sub))
    return out


def _rewrite(link, items, new_target):
    """Retarget `link` and write the new subnames: items = [(ref, new inner)]."""
    par_prop = {}
    for (o, p, t, i, j, k, sub), new_inner in items:
        objets, _mapped, _elem = freeze.decouper_sub(sub)
        prefix = ".".join(objets[:k + 1])
        par_prop.setdefault((o, p, t), []).append(
            (i, j, (prefix + "." if prefix else "") + new_inner))
    link.LinkedObject = new_target
    for (o, p, t), lst in par_prop.items():
        refs = freeze._lire(o, p, t)
        for i, j, new_sub in lst:
            refs[i][1][j] = new_sub
        try:
            setattr(o, p, [] if "List" in t else None)    # flush hidden names
            freeze._ecrire(o, p, t, refs)
        except Exception as e:
            App.Console.PrintWarning(tr("Lightweight: cannot write {obj}.{prop}: {error}")
                                     .format(obj=o.Label, prop=p, error=e) + "\n")


def _skin(shape, diag):
    import MeshPart
    return MeshPart.meshFromShape(Shape=shape, LinearDeflection=diag * LINEAR,
                                  AngularDeflection=ANGULAR, Relative=False)


def _pieces(target, prefix="", depth=0):
    """[(subname, object)] of the solids shown by `target`, one per body, so
    each skin keeps the colour of its body. Walks Std_Parts, assemblies and
    the Links inside them, so a whole sub-assembly can become one
    lightweight component."""
    if depth > 30:
        return []
    if target.isDerivedFrom("App::Part"):
        out = []
        from .bom import _children, _skip
        for c in _children(target):
            if c.isDerivedFrom("App::Origin") or _skip(c):
                continue
            if c.isDerivedFrom("App::Link"):
                t = c.getLinkedObject(True)
                if t is None:
                    continue
                if t.isDerivedFrom("App::Part"):
                    out += _pieces(t, prefix + c.Name + ".", depth + 1)
                else:
                    out.append((prefix + c.Name + ".", t))
            elif c.isDerivedFrom("App::Part"):
                out += _pieces(c, prefix + c.Name + ".", depth + 1)
            elif _is_skin(c):
                # skin of a lightweight component nested in a sub-assembly
                out.append((prefix + c.Name + ".", c))
            else:
                try:
                    if c.isDerivedFrom("Part::Feature") and c.Shape.Solids:
                        out.append((prefix + c.Name + ".", c))
                except Exception:
                    pass
        return out
    return [(prefix, target)]


def _color(o):
    """Display colour of `o` as an App.Material, or None (no GUI)."""
    vo = getattr(o, "ViewObject", None)
    if vo is None:
        return None
    try:
        if "Color" in vo.PropertiesList and _is_skin(o):       # LOD skin
            c = vo.Color
            return App.Material(DiffuseColor=(c[0], c[1], c[2]))
        app = vo.ShapeAppearance
        return app[0] if app else None
    except Exception:
        return None


# ----------------------------------------------------------------------
#  Skin with level of detail (Coin3D SoLOD)
# ----------------------------------------------------------------------
class Skin(object):
    """App proxy of a skin: a plain App::FeaturePython carrying the mesh in a
    Mesh property (a Mesh::FeaturePython would bring the native mesh view
    provider, which does not handle a custom display mode)."""

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("Mesh::PropertyMeshKernel", "Mesh", "Lightweight", "Skin mesh")
        obj.addProperty("App::PropertyFloat", "LodPixels", "Lightweight",
                        "Below this screen area (pixels) the skin is drawn as a box "
                        "(0: always the mesh)")

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderSkin(object):
    """Draws the mesh when the part is big enough on screen, its bounding box
    when it is small (SoLevelOfDetail, chosen by Coin at each frame from the
    projected screen area: works with the orthographic camera FreeCAD uses
    by default, where zooming does not change the camera distance and a
    distance-based SoLOD never switches). Nothing changes in the document
    while navigating."""

    def __init__(self, vobj):
        vobj.addProperty("App::PropertyColor", "Color", "Lightweight", "Skin colour")
        vobj.Proxy = self

    def attach(self, vobj):
        from pivy import coin
        self.Object = vobj.Object
        self.root = coin.SoSeparator()
        self.material = coin.SoMaterial()
        self.material.diffuseColor = (0.8, 0.8, 0.8)
        self.root.addChild(self.material)
        self.lod = coin.SoLevelOfDetail()
        self.root.addChild(self.lod)
        vobj.addDisplayMode(self.root, "LOD")
        self._build(vobj.Object)
        self._color(vobj)

    def _build(self, obj):
        from pivy import coin
        self.lod.removeAllChildren()
        mesh = obj.Mesh
        if mesh.CountFacets == 0:
            return
        points, facets = mesh.Topology
        near = coin.SoSeparator()
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.creaseAngle = 0.6
        near.addChild(hints)
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(points), [(p.x, p.y, p.z) for p in points])
        near.addChild(coords)
        faces = coin.SoIndexedFaceSet()
        idx = []
        for f in facets:
            idx += [f[0], f[1], f[2], -1]
        faces.coordIndex.setValues(0, len(idx), idx)
        near.addChild(faces)
        self.lod.addChild(near)
        bb = mesh.BoundBox
        pixels = getattr(obj, "LodPixels", 0.0)
        if pixels > 0:
            far = coin.SoSeparator()
            tr_ = coin.SoTranslation()
            tr_.translation = (bb.Center.x, bb.Center.y, bb.Center.z)
            box = coin.SoCube()
            box.width, box.height, box.depth = (max(bb.XLength, 1e-3),
                                                max(bb.YLength, 1e-3),
                                                max(bb.ZLength, 1e-3))
            far.addChild(tr_)
            far.addChild(box)
            self.lod.addChild(far)
            self.lod.screenArea.setValues(0, 1, [float(pixels)])

    def _color(self, vobj):
        try:
            c = vobj.Color
            self.material.diffuseColor = (c[0], c[1], c[2])
        except Exception:
            pass

    def updateData(self, obj, prop):
        if prop in ("Mesh", "LodPixels") and hasattr(self, "lod"):
            self._build(obj)

    def onChanged(self, vobj, prop):
        if prop == "Color" and hasattr(self, "material"):
            self._color(vobj)

    def getDisplayModes(self, vobj):
        return ["LOD"]

    def getDefaultDisplayMode(self):
        return "LOD"

    def setDisplayMode(self, mode):
        return mode

    def getIcon(self):
        from . import icon
        return icon("Lightweight.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None


def _new_skin(doc, mesh):
    """Skin object: a native Mesh::Feature, so that the file shows its skins
    in a FreeCAD without this addon. The level of detail is a dynamic
    LodPixels property (a plain float, kept by any FreeCAD) used by
    attach_lod() when the addon is there; 0 or absent = always the mesh.
    (Skins of version 0.1.0 are App::FeaturePython objects with the Skin /
    ViewProviderSkin proxies above; they keep working.)"""
    from . import prefs
    sn = doc.addObject("Mesh::Feature", "Skin")
    sn.Mesh = mesh
    pixels = prefs.get("LightweightLodPixels")
    if pixels > 0:
        sn.addProperty("App::PropertyFloat", "LodPixels", "Lightweight",
                       "Below this screen area (pixels) the skin is drawn as a box "
                       "(0: always the mesh)")
        sn.LodPixels = float(pixels)
    return sn


# ----------------------------------------------------------------------
#  Level of detail on native skins (GUI, nothing stored in the document)
# ----------------------------------------------------------------------
def attach_lod(obj):
    """Wrap each display mode of the native mesh view provider of a skin in
    a SoLevelOfDetail: the mesh when the skin covers more than LodPixels on
    screen, its bounding box below (projected area, see ViewProviderSkin).
    Only the scene graph changes; Links share it. Idempotent: called again,
    it updates the box and the threshold."""
    if not App.GuiUp or "LodPixels" not in obj.PropertiesList or \
            not obj.isDerivedFrom("Mesh::Feature"):
        return False
    # pivy first: FreeCAD can only hand out Coin nodes (SwitchNode) once the
    # SWIG wrapper is loaded ("No SWIG wrapped library loaded" otherwise)
    from pivy import coin
    vobj = obj.ViewObject
    sw = getattr(vobj, "SwitchNode", None) if vobj is not None else None
    if sw is None:
        return False
    bb = obj.Mesh.BoundBox
    far = coin.SoSeparator()
    far.setName("AC_LodBox")
    tr_ = coin.SoTranslation()
    tr_.translation = (bb.Center.x, bb.Center.y, bb.Center.z)
    box = coin.SoCube()
    box.width, box.height, box.depth = (max(bb.XLength, 1e-3), max(bb.YLength, 1e-3),
                                        max(bb.ZLength, 1e-3))
    far.addChild(tr_)
    far.addChild(box)
    pixels = float(obj.LodPixels)
    for i in range(sw.getNumChildren()):
        child = sw.getChild(i)
        if child.isOfType(coin.SoLevelOfDetail.getClassTypeId()) and \
                child.getName().getString() == "AC_Lod":
            lod = child
            lod.replaceChild(1, far)
        else:
            lod = coin.SoLevelOfDetail()
            lod.setName("AC_Lod")
            lod.addChild(child)            # referenced before it leaves the switch
            lod.addChild(far)
            sw.replaceChild(i, lod)
        lod.screenArea.setValues(0, 1, [pixels if pixels > 0 else 0.0])
    return True


def attach_lod_document(doc):
    n = 0
    for o in doc.Objects:
        try:
            n += bool(attach_lod(o))
        except Exception as exc:
            App.Console.PrintLog("Lightweight LOD: %s (%s)\n" % (o.Name, exc))
    return n


class _LodObserver(object):
    """Attaches the level of detail to native skins when a document is
    opened, when a skin is created (also by undo / redo) or changed. Deferred
    to the event loop: the view provider does not exist yet in these slots."""

    def _later(self, fn):
        try:
            from PySide import QtCore
        except ImportError:
            from PySide6 import QtCore
        QtCore.QTimer.singleShot(0, fn)

    def slotFinishRestoreDocument(self, doc):
        name = doc.Name
        self._later(lambda: name in App.listDocuments() and
                    attach_lod_document(App.getDocument(name)))

    def _object_later(self, obj):
        dn, on = obj.Document.Name, obj.Name

        def run():
            d = App.listDocuments().get(dn)
            o = d.getObject(on) if d is not None else None
            if o is not None:
                try:
                    attach_lod(o)
                except Exception as exc:
                    App.Console.PrintLog("Lightweight LOD: %s (%s)\n" % (on, exc))
        self._later(run)

    def slotCreatedObject(self, obj):
        if obj.isDerivedFrom("Mesh::Feature"):
            self._object_later(obj)

    def slotChangedObject(self, obj, prop):
        if prop in ("LodPixels", "Mesh") and "LodPixels" in obj.PropertiesList:
            self._object_later(obj)


_lod_observer = None


def install():
    """Called at GUI startup (init_gui)."""
    global _lod_observer
    if _lod_observer is None and App.GuiUp:
        _lod_observer = _LodObserver()
        App.addDocumentObserver(_lod_observer)


def make(doc, links):
    """Turn `links` into lightweight components. Returns the containers."""
    import Part
    by_target = {}
    for l in links:
        t = l.LinkedObject
        if t is None or is_lightweight(t):
            continue
        by_target.setdefault((t.Document.Name, t.Name), (t, []))[1].append(l)
    created = []
    for target, group_links in by_target.values():
        first = group_links[0]
        full = Part.getShape(first, transform=False)
        if full.isNull():
            App.Console.PrintWarning(tr("Lightweight: “{name}” has no shape, skipped.")
                                     .format(name=first.Label) + "\n")
            continue
        refs = {l.Name: _element_refs(l) for l in group_links}
        # Skeleton: every element used by a joint of any instance, once
        elements, order = {}, []
        for lst in refs.values():
            for _ref, inner in lst:
                if inner in elements or not freeze.decouper_sub(inner)[2]:
                    continue
                try:
                    sh = Part.getShape(first, inner, needSubElement=True, transform=False)
                except Exception:
                    sh = None
                if sh is not None and not sh.isNull():
                    elements[inner] = sh
                    order.append(inner)
        skeleton = Part.makeCompound([elements[i] for i in order]) if order else Part.Shape()
        mapping = {}
        for inner in order:
            sh = elements[inner]
            pool = {"Face": skeleton.Faces, "Edge": skeleton.Edges,
                    "Vertex": skeleton.Vertexes}[sh.ShapeType]
            for n, e in enumerate(pool, 1):
                if e.isSame(sh):
                    mapping[inner] = "%s%d" % (sh.ShapeType, n)
                    break

        src_file, src_obj, src_label = _source(target, doc)
        cont = doc.addObject("App::Part", "LW")
        cont.Label = "LW_" + src_label
        was_frozen = freeze._est_fige(target)
        for name, typ, doc_ in (("LWFile", "App::PropertyString", "Source file"),
                                ("LWObject", "App::PropertyString", "Source object"),
                                ("LWLabel", "App::PropertyString", "Source label"),
                                ("LWWasFrozen", "App::PropertyBool", "Frozen before"),
                                ("LWMap", "App::PropertyStringList", "Element mapping")):
            cont.addProperty(typ, name, "Lightweight", doc_)
        cont.LWFile, cont.LWObject, cont.LWLabel = src_file or "", src_obj, src_label
        cont.LWWasFrozen = was_frozen
        cont.LWMap = ["%s|%s" % (_source_inner(k, doc) if was_frozen else k, v)
                      for k, v in mapping.items()]
        _group(doc).addObject(cont)

        sk = doc.addObject("Part::Feature", "Skeleton")
        sk.Label = tr("Skeleton")
        sk.Shape = skeleton
        cont.addObject(sk)
        diag = max(full.BoundBox.DiagonalLength, 1.0)
        # One mesh per piece, then merged per colour: a sub-assembly of a
        # thousand parts gives a handful of skins, not a thousand objects
        by_color, names = {}, {}
        for sub, obj in _pieces(target):
            if _is_skin(obj):
                # Nested lightweight component: reuse its mesh, placed through
                # the path (matrix in the Link's own coordinates)
                mesh = obj.Mesh.copy()
                mesh.transform(first.getSubObject(sub, retType=4, transform=False))
            else:
                shape = Part.getShape(first, sub, needSubElement=True, transform=False) \
                    if sub else full
                if shape.isNull():
                    continue
                mesh = _skin(shape, diag)
            col = _color(obj)
            key = tuple(round(c, 3) for c in col.DiffuseColor[:3]) if col is not None else None
            if key in by_color:
                by_color[key][0].addMesh(mesh)
            else:
                by_color[key] = [mesh, col]
            label = obj.Label if _is_skin(obj) else (
                (obj.FigeLabel or obj.Label) if freeze._est_fige(obj) else obj.Label)
            names.setdefault(key, []).append(label)
        skins = []
        for key, (mesh, col) in by_color.items():
            sn = _new_skin(doc, mesh)
            lbl = names[key]
            sn.Label = lbl[0] if len(lbl) == 1 else tr("Skin") + " (%d)" % len(lbl)
            cont.addObject(sn)
            skins.append((sn, col))
        if App.GuiUp:
            try:
                cont.ViewObject.Visibility = False      # shown through the Links
                sk.ViewObject.LineColor = (0.9, 0.5, 0.0)
                sk.ViewObject.PointColor = (0.9, 0.5, 0.0)
                sk.ViewObject.LineWidth = 2.0
                sk.ViewObject.Transparency = 70
                for sn, col in skins:
                    if col is None:
                        continue
                    if "Color" in sn.ViewObject.PropertiesList:     # LOD skin
                        sn.ViewObject.Color = tuple(col.DiffuseColor[:3])
                    else:
                        sn.ViewObject.ShapeAppearance = [col]
                for sn, _col in skins:
                    attach_lod(sn)
            except Exception:
                pass

        for l in group_links:
            # Child names are unique in the document: Skeleton, Skeleton001...
            items = [(ref, sk.Name + "." + mapping[inner]) for ref, inner in refs[l.Name]
                     if inner in mapping]
            _rewrite(l, items, cont)
        # The frozen copy, if no other Link uses it, would keep its BREP in
        # the file: delete it (restoring freezes the source again)
        if was_frozen and not any(freeze._est_lien(o) and o.LinkedObject is target
                                  for o in doc.Objects):
            freeze._supprimer_fige(doc, target)
        created.append(cont)
        App.Console.PrintMessage(tr("Lightweight: “{name}” -> {n} instance(s), skeleton of "
                                    "{e} element(s), skin of {f} facets.").format(
            name=src_label, n=len(group_links), e=len(order),
            f=sum(sn.Mesh.CountFacets for sn, _c in skins)) + "\n")
    return created


def source_path(cont, doc):
    """Source file of a lightweight component, or None: the stored absolute
    path, then the same file name next to the assembly (project folder moved
    or copied to another computer, as freeze.chemin_source does)."""
    candidates = [cont.LWFile]
    if cont.LWFile and doc is not None and doc.FileName:
        candidates.append(os.path.join(os.path.dirname(doc.FileName),
                                       os.path.basename(cont.LWFile)))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def restore(doc, links):
    """Point lightweight `links` back to their source object, joints too, and
    freeze them again when they were frozen."""
    from . import docs
    done, to_freeze = [], []
    for l in links:
        cont = l.LinkedObject
        if not is_lightweight(cont):
            continue
        path = source_path(cont, doc)
        if path is None:
            App.Console.PrintWarning(tr("Lightweight: source of “{name}” not found ({file}).")
                                     .format(name=l.Label, file=cont.LWFile or "?") + "\n")
            continue
        src_doc = docs.open_source(path, keep=doc)
        src = src_doc.getObject(cont.LWObject)
        if src is None:
            App.Console.PrintWarning(tr("Lightweight: object {obj} not found in {file}.")
                                     .format(obj=cont.LWObject, file=cont.LWFile) + "\n")
            continue
        sk, _skins = _children(cont)
        back = {}
        for entry in cont.LWMap:
            inner, _sep, new = entry.rpartition("|")
            back[sk.Name + "." + new] = inner
        items = [(ref, back[inner]) for ref, inner in _element_refs(l) if inner in back]
        _rewrite(l, items, src)
        done.append(l)
        if cont.LWWasFrozen:
            to_freeze.append(l)
        # Container no longer used by any Link: delete it
        if not any(freeze._est_lien(o) and o.LinkedObject is cont for o in doc.Objects):
            for c in list(cont.Group):
                doc.removeObject(c.Name)
            doc.removeObject(cont.Name)
    g = doc.getObject(GROUP)
    if g is not None and not g.Group:
        doc.removeObject(g.Name)
    return done, to_freeze


# ----------------------------------------------------------------------
#  Commands
# ----------------------------------------------------------------------
def _components(doc, lightweight):
    """Selected components (Links), else every Link of the assembly that is
    (lightweight=True: not yet) / (False: already) lightweight."""
    links = freeze.selection_composants() if App.GuiUp else []
    links = [l for l in links if freeze._est_lien(l)]
    if not links:
        from . import bom
        roots = bom.roots_of(doc)
        links = [o for o in doc.Objects if freeze._est_lien(o) and o.LinkedObject is not None
                 and any(r in o.InListRecursive for r in roots)]
    want = (lambda l: not is_lightweight(l.LinkedObject)) if lightweight else \
        (lambda l: is_lightweight(l.LinkedObject))
    return [l for l in links if want(l)]


def make_command(doc=None):
    from . import docs
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    links = _components(doc, True)
    if not links:
        raise RuntimeError(tr("No component to lighten (select components, or none for "
                              "the whole assembly)."))
    doc.openTransaction(tr("Make lightweight"))
    try:
        made = make(doc, links)
        freeze.marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()
    return made


def restore_command(doc=None):
    from . import docs
    doc = doc or docs.working_document()
    if doc is None:
        raise RuntimeError(tr("No active document."))
    links = _components(doc, False)
    if not links:
        raise RuntimeError(tr("No lightweight component selected or in the assembly."))
    doc.openTransaction(tr("Restore full components"))
    try:
        done, to_freeze = restore(doc, links)
        doc.recompute()
    finally:
        doc.commitTransaction()
    if to_freeze:
        freeze.figer(doc, to_freeze)
    from . import docs
    docs.activate(doc)
    App.Console.PrintMessage(tr("Lightweight: {n} component(s) restored.").format(
        n=len(done)) + "\n")
    return done


def _show_target(d, obj_name):
    """Select the source object in its document and fit the view to it,
    without changing the document (hiding the other objects would mark it
    modified, and FreeCAD would then ask to save it with the assembly)."""
    import FreeCADGui as Gui
    o = d.getObject(obj_name) if obj_name else None
    if o is None:
        return None
    try:
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(d.Name, o.Name)
        Gui.SendMsgToActiveView("ViewSelection")
    except Exception:
        pass
    return o


def _other_parts(d, obj_name):
    """Other bodies / parts of the source file (a file holding every part
    of the assembly is loaded whole when one of them is opened)."""
    return [o.Label for o in d.Objects if o.Name != obj_name and
            (o.isDerivedFrom("PartDesign::Body") or o.TypeId == "App::Part") and
            o.getParentGeoFeatureGroup() is None]


def open_source_command(doc=None):
    """Open the real file of the selected component (lightweight, frozen or
    linked) to work on it: only that file is loaded (fully, to be editable),
    the source part is selected and the view fitted to it. A file that holds
    several parts is reported (Extract bodies gives one file per part)."""
    import FreeCADGui as Gui
    from . import docs
    doc = doc or docs.working_document()
    links = [l for l in (freeze.selection_composants() if App.GuiUp else [])
             if freeze._est_lien(l) and l.LinkedObject is not None]
    if not links:
        raise RuntimeError(tr("Select a component of the assembly."))
    t = links[0].LinkedObject
    if is_lightweight(t):
        path, obj_name = source_path(t, doc), t.LWObject
    else:
        path, obj_name, _label = _source(t, doc)
    if not path or not os.path.isfile(path):
        raise RuntimeError(tr("Source file not found: {file}").format(file=path or "?"))
    d = None
    for x in App.listDocuments().values():
        if docs.same_file(x.FileName, path):
            d = x
    if d is not None:
        # Already loaded for the assembly, hidden and maybe partially: never
        # close it (its linked parts would vanish); load what is missing of
        # THIS file only (a partial document cannot be edited) and give it a view
        try:
            if getattr(d, "Partial", False):
                d.restore()
        except Exception:
            pass
        App.setActiveDocument(d.Name)
        Gui.setActiveDocument(d.Name)
        if not Gui.getDocument(d.Name).mdiViewsOfType("Gui::View3DInventor"):
            Gui.runCommand("Std_ViewCreate", 0)
    else:
        d = App.openDocument(path)
        App.setActiveDocument(d.Name)
    _show_target(d, obj_name)
    others = _other_parts(d, obj_name)
    if others:
        App.Console.PrintMessage(tr("Open source: {file} also holds {n} other part(s) ({names}): "
                                    "the whole file is loaded. “Extract bodies” gives one file "
                                    "per part.").format(file=os.path.basename(path), n=len(others),
                                                       names=", ".join(others[:6])) + "\n")
    return d
