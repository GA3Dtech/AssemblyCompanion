# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - freeze / relink
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
freeze.py (Assembly Companion) - Freeze / relink components of an assembly made with
FreeCAD's built-in Assembly workbench, A2plus style.

Principle:
  * FREEZE : every App::Link pointing to a Body in ANOTHER file is retargeted
             to a "dead" copy (Part::Feature, plain BREP solid without any
             topological history) stored in the assembly file. A Link to an
             App::Part gets a frozen App::Part holding a dead copy of each
             of its Bodies, at the same place. The assembly
             no longer depends on the source files, nor on how a future
             FreeCAD version recomputes them.
  * RELINK : the opposite, the Link points again to the Body of the source
             file (to edit a part, then freeze again).
  * DELETE JOINTS : remove every joint (and the grounding) of selected parts.
  * DIAGNOSTIC / REPAIR : check that every joint reference resolves, and
             clean copies frozen with early versions of this module.

Source metadata (file, object, date, FreeCAD version) is stored on each copy,
in the "Figeage" property group.

Recommended workflow for a modified part:
  select the part -> Relink -> edit the source -> fix joints -> Freeze.

User-facing texts are in English, translated through i18n.tr().

v1.0 - first consolidated version (tested on FreeCAD 26.3rc2).
       History: references cleared then rewritten after retargeting (no more
       '?' elements on reopening), copies without topological history,
       robust selection (tree, 3D view, frozen copy).
"""

import os
import re
import datetime

import FreeCAD as App
import Part

from .i18n import tr

from .version import __version__ as VERSION  # single source: package.xml
GROUPE_COPIES = "Solides_figes"     # group holding the frozen copies
GROUPE_INUTILES = "Solides_figes_inutilises"   # sub-group: copies no Link uses

# Matches the trailing element of a subname: "...Face6", "...Edge12", "...Vertex3"
_RE_ELEM = re.compile(r'(?:^|\.)((?:Face|Edge|Vertex)\d+)$')
_RE_ELEM_NUM = re.compile(r'^(Face|Edge|Vertex)(\d+)$')


# --------------------------------------------------------------------------
#  Subname handling (pure logic, testable outside FreeCAD)
# --------------------------------------------------------------------------

def decouper_sub(sub):
    """Split a subname into (object path, mapped name, element).
    'Link.Pad.;#mapped;.Face6' -> (['Link', 'Pad'], ';#mapped;', 'Face6')
    'Link.Body.'               -> (['Link', 'Body'], '', '')"""
    # '?' is the "missing element" marker set by FreeCAD: strip it
    sub = sub.lstrip('?').replace('.?', '.')
    elem = ''
    reste = sub
    m = _RE_ELEM.search(sub)
    if m:
        elem = m.group(1)
        reste = sub[:m.start(1)]
    # A mapped (topological naming) segment starts with ';'
    mapped = ''
    idx = 0 if reste.startswith(';') else (reste.find('.;') + 1 if '.;' in reste else -1)
    if idx >= 0:
        mapped = reste[idx:].rstrip('.')
        reste = reste[:idx]
    objets = [s for s in reste.split('.') if s]
    return objets, mapped, elem


def reecrire_sub(sub, k, remap=None):
    """Keep the path up to the Link (objets[:k+1]), drop the path inside the
    Link target and the mapped topological name, keep the element (optionally
    renumbered through remap). k = -1 when the reference starts at the Link."""
    objets, _mapped, elem = decouper_sub(sub)
    if remap and elem in remap and remap[elem]:
        elem = remap[elem]
    prefixe = '.'.join(objets[:k + 1])
    if prefixe:
        prefixe += '.'
    return prefixe + elem


def reecrire_sub_chemins(sub, k, chemins):
    """Same as reecrire_sub, for a Link to an App::Part container: the path
    inside the container is kept, each object name translated through
    `chemins` = {old name: (new name, sub-mapping or None)}. A None
    sub-mapping marks a leaf (frozen solid, origin feature): what follows it
    in the path (features inside a Body) is dropped, like reecrire_sub does.
    Unknown names are kept as they are (the reference shows up as broken in
    the diagnostic instead of silently pointing elsewhere)."""
    objets, _mapped, elem = decouper_sub(sub)
    chemin = list(objets[:k + 1])
    niveau = chemins
    for nom in objets[k + 1:]:
        if niveau is None:
            break
        if nom not in niveau:
            chemin.append(nom)
            niveau = {}
            continue
        nouveau, niveau = niveau[nom]
        chemin.append(nouveau)
    prefixe = '.'.join(chemin)
    if prefixe:
        prefixe += '.'
    return prefixe + elem


# --------------------------------------------------------------------------
#  FreeCAD helpers
# --------------------------------------------------------------------------

def _est_lien(o):
    return o.isDerivedFrom('App::Link')


def _est_copie_figee(o):
    # Careful: an App::Link forwards its target's attributes, so hasattr() is
    # not enough -- check the object's own property list.
    return o is not None and not _est_lien(o) and o.isDerivedFrom('Part::Feature') \
        and 'FigeObjet' in o.PropertiesList


def _est_conteneur_fige(o):
    """Frozen copy of an App::Part container (holds frozen copies)."""
    return o is not None and not _est_lien(o) and o.isDerivedFrom('App::Part') \
        and 'FigeObjet' in o.PropertiesList


def _est_fige(o):
    return _est_copie_figee(o) or _est_conteneur_fige(o)


def _est_lien_fige(o):
    """Link made by the freeze inside a frozen container (component of a
    frozen sub-assembly, element of an imported STEP group), or a shared
    frozen copy of a source Link (Link to a Link)."""
    return o is not None and _est_lien(o) and 'FigeObjet' in o.PropertiesList


def _est_assemblage_obj(o):
    return o is not None and o.isDerivedFrom('Assembly::AssemblyObject')


def _est_assemblage_lien(o):
    """Sub-assembly inserted by the Assembly workbench of FreeCAD 26.x: an
    App::Part whose children are Links to the components of LinkedObject."""
    return o is not None and o.TypeId == 'Assembly::AssemblyLink'


def _parent_assemblage_lien(o):
    """Outermost sub-assembly holding `o` (sub-assemblies mirror their
    nested sub-assemblies as nested Assembly::AssemblyLink children), or
    None."""
    racine, cur = None, o
    for _i in range(30):
        p = None
        for q in cur.InList:
            if _est_assemblage_lien(q) and cur in q.Group:
                p = q
        if p is None:
            break
        racine = cur = p
    return racine


def _est_assemblage_lien_fige(o):
    return _est_assemblage_lien(o) and 'FigeObjet' in o.PropertiesList


def _conteneur_racine(o):
    """Outermost frozen container holding `o`, or None."""
    racine = None
    p = o.getParentGeoFeatureGroup() if o is not None else None
    while p is not None:
        if _est_conteneur_fige(p):
            racine = p
        p = p.getParentGeoFeatureGroup()
    return racine


def liens_externes(doc, selection=None):
    """Links and sub-assemblies (Assembly::AssemblyLink) pointing to another
    document: the candidates for freezing. The children of a sub-assembly
    are frozen with it, never one by one."""
    objs = doc.Objects if selection is None else selection
    out = []
    for o in objs:
        al = _parent_assemblage_lien(o) if (_est_lien(o) or _est_assemblage_lien(o)) else None
        if al is not None:
            o = al                      # a component picked inside a sub-assembly
        if o in out or not (_est_lien(o) or _est_assemblage_lien(o)):
            continue
        if _est_lien_fige(o) or _est_assemblage_lien_fige(o) or o.LinkedObject is None:
            continue
        if o.LinkedObject.Document is not doc:
            out.append(o)
    return out


def liens_figes(doc, selection=None):
    """Links and sub-assemblies pointing to a frozen copy or container (the
    candidates for relinking); Links made by the freeze inside frozen
    containers follow their container."""
    objs = doc.Objects if selection is None else selection
    out = []
    for o in objs:
        al = _parent_assemblage_lien(o) if (_est_lien(o) or _est_assemblage_lien(o)) else None
        if al is not None:
            o = al
        if o in out or _est_assemblage_lien_fige(o):
            continue
        if _est_lien(o) and not _est_lien_fige(o) and _est_fige(o.LinkedObject):
            out.append(o)
        elif _est_assemblage_lien(o) and _est_conteneur_fige(o.LinkedObject):
            out.append(o)
    return out


def _index_lien(base, objets, lien):
    """Position of the Link in the reference path, -1 if the reference starts
    at the Link itself, None if the reference does not go through it."""
    if base is lien:
        return -1
    try:
        chaine = base.getSubObjectList('.'.join(objets) + '.')
        for i, o in enumerate(chaine[1:]):
            if o.Document is lien.Document and o.Name == lien.Name:
                return i
        return None
    except Exception:
        pass
    if base.Document is lien.Document and lien.Name in objets:  # fallback by name
        return objets.index(lien.Name)
    return None


def _proprietes_refs(doc, exclure=()):
    """Yield (object, property, type) for every LinkSub* property of the doc
    (joint references are App::PropertyXLinkSubHidden)."""
    for o in doc.Objects:
        if o in exclure:
            continue
        for p in o.PropertiesList:
            try:
                t = o.getTypeIdOfProperty(p)
            except Exception:
                continue
            if 'LinkSub' in t:
                yield o, p, t


def _lire(o, p, t):
    """Read a LinkSub* property as a list of (base, [subnames])."""
    v = getattr(o, p)
    if not v:
        return []
    if 'List' in t:
        return [(b, [s] if isinstance(s, str) else list(s)) for b, s in v]
    b, s = v
    return [(b, [s] if isinstance(s, str) else list(s))]


def _ecrire(o, p, t, refs):
    """Write back a list of (base, [subnames]) into a LinkSub* property."""
    if 'List' in t:
        setattr(o, p, [(b, tuple(s)) for b, s in refs])
    else:
        b, s = refs[0]
        setattr(o, p, (b, s))


def references_via(lien):
    """List of (object, property, type, i_ref, i_sub, k, sub) for every
    reference of the document that goes through `lien`."""
    doc = lien.Document
    res = []
    for o, p, t in _proprietes_refs(doc, exclure=(lien,)):
        for i, (base, subs) in enumerate(_lire(o, p, t)):
            if base is None:
                continue
            for j, sub in enumerate(subs):
                objets, _m, _e = decouper_sub(sub)
                k = _index_lien(base, objets, lien)
                if k is not None:
                    res.append((o, p, t, i, j, k, sub))
    return res


def appliquer_reecriture(lien, remap=None, nouvelle_cible=None, chemins=None,
                         fonction=None):
    """Rewrite every reference going through `lien`, after optionally
    retargeting the Link. With `chemins` (Link to an App::Part container),
    the path inside the target is translated instead of dropped; with
    `fonction(sub, k)` (frozen blocks) each subname is rewritten by it.
    Each reference is CLEARED then written again, even
    when its text does not change: otherwise FreeCAD keeps internally the
    topological name computed on the previous target, saves it, and cannot
    resolve it on reopening (element marked '?', broken joint).
    Returns the number of references processed."""
    par_prop = {}
    for o, p, t, i, j, k, sub in references_via(lien):
        par_prop.setdefault((o, p, t), []).append((i, j, k, sub))
    if nouvelle_cible is not None:
        lien.LinkedObject = nouvelle_cible
    n = 0
    for (o, p, t), items in par_prop.items():
        refs = _lire(o, p, t)
        for i, j, k, sub in items:
            if fonction is not None:
                refs[i][1][j] = fonction(sub, k)
            elif chemins is not None:
                refs[i][1][j] = reecrire_sub_chemins(sub, k, chemins)
            else:
                refs[i][1][j] = reecrire_sub(sub, k, remap)
            n += 1
        try:
            setattr(o, p, [] if 'List' in t else None)   # flush hidden names
            _ecrire(o, p, t, refs)
        except Exception as e:
            App.Console.PrintWarning(
                tr("Freeze: cannot write {obj}.{prop}: {error}").format(
                    obj=o.Label, prop=p, error=e) + "\n")
    return n


def _groupe(doc, nom):
    g = doc.getObject(nom)
    if g is None:
        g = doc.addObject('App::DocumentObjectGroup', nom)
    return g


def _version_fc():
    return '.'.join(App.Version()[:3])


def chemin_source(copie, doc_asm):
    """Source file of a frozen copy, or None. Tries the path relative to the
    assembly first (project folder moved), then the absolute path, then the
    same file name next to the assembly."""
    candidats = []
    if doc_asm.FileName and copie.FigeFichierRelatif:
        candidats.append(os.path.normpath(os.path.join(
            os.path.dirname(doc_asm.FileName), copie.FigeFichierRelatif)))
    candidats.append(copie.FigeFichier)
    if doc_asm.FileName:
        candidats.append(os.path.join(os.path.dirname(doc_asm.FileName),
                                      os.path.basename(copie.FigeFichier)))
    for chemin in candidats:
        if chemin and os.path.isfile(chemin):
            return chemin
    return None


def _ouvrir_source(copie, doc_asm):
    """Find and open the source document of a frozen copy (see
    chemin_source). Returns (document, opened_by_us)."""
    chemin = chemin_source(copie, doc_asm)
    if chemin is not None:
        for d in App.listDocuments().values():
            if d.FileName and os.path.samefile(d.FileName, chemin):
                return d, False
        # Hidden, and the assembly stays the active document (see docs.py)
        from . import docs
        return docs.open_source(chemin, keep=doc_asm), True
    return None, False


def _objet_source(copie, doc_src):
    """Source object of a copy: by internal name, then by label."""
    o = doc_src.getObject(copie.FigeObjet)
    if o is None:
        lst = doc_src.getObjectsByLabel(copie.FigeLabel)
        o = lst[0] if lst else None
    return o


# --------------------------------------------------------------------------
#  FREEZE
# --------------------------------------------------------------------------

def _trouver_copie(doc, src, parent=None, test=None):
    """Existing frozen copy of `src` in the assembly (one copy per source
    object, shared by all its instances). `parent` is the frozen container
    the copy belongs to (None: a stand-alone copy, outside any container), so
    a Body frozen on its own and the same Body frozen inside its Part get two
    separate copies."""
    test = test or _est_copie_figee
    fichier = src.Document.FileName
    for o in doc.Objects:
        if test(o) and o.FigeObjet == src.Name and \
                os.path.basename(o.FigeFichier) == os.path.basename(fichier) and \
                o.getParentGeoFeatureGroup() is parent:
            return o
    return None


def _proprietes_figeage(obj, src, doc):
    """Create (once) and fill the source metadata of a frozen object."""
    for nom in ('FigeFichier', 'FigeFichierRelatif', 'FigeObjet',
                'FigeLabel', 'FigeDate', 'FigeVersionFC'):
        if nom not in obj.PropertiesList:
            obj.addProperty('App::PropertyString', nom, 'Figeage')
    obj.FigeFichier = src.Document.FileName
    obj.FigeFichierRelatif = (os.path.relpath(src.Document.FileName,
                              os.path.dirname(doc.FileName))
                              if doc.FileName and src.Document.FileName else '')
    obj.FigeObjet = src.Name
    obj.FigeLabel = src.Label
    obj.FigeDate = datetime.datetime.now().isoformat(timespec='seconds')
    obj.FigeVersionFC = _version_fc()


def forme_propre(shape):
    """'Dead' copy through a BREP round trip: same geometry, same numbering of
    faces / edges / vertices, but NO topological history (element map) that
    would point back to the source document and break joints on reopening."""
    s = Part.Shape()
    s.importBrepFromString(shape.exportBrepToString())
    return s


def forme_source(src):
    """Shape a frozen copy of `src` must hold. A Body whose Tip gives no
    shape (e.g. a Body holding only a SubShapeBinder, as made by "New part
    from selection") shows its visible members: their shapes are gathered,
    in the Body's coordinates, with the Body's placement. Null when there
    is nothing to show."""
    sh = src.Shape
    if not sh.isNull() or not src.isDerivedFrom('PartDesign::Body'):
        return sh
    formes = []
    for m in src.Group:
        try:
            if not m.Visibility or m.isDerivedFrom('App::Origin'):
                continue
            f = Part.getShape(src, m.Name + '.', needSubElement=False, transform=False)
        except Exception:
            continue
        if not f.isNull():
            formes.append(f)
    if not formes:
        return sh
    c = formes[0].copy() if len(formes) == 1 else Part.makeCompound(formes)
    c.Placement = src.Placement.multiply(c.Placement)
    return c


def _creer_ou_rafraichir_copie(doc, src, parent=None):
    """Frozen copy of the solid `src`. Stand-alone copies are stored hidden in
    the Solides_figes group (the Link displays them); copies inside a frozen
    container stay visible, since a Link to a container only shows its
    visible children."""
    copie = _trouver_copie(doc, src, parent)
    if copie is None:
        copie = doc.addObject('Part::Feature', 'Fige_' + src.Name)
        if parent is None:
            _groupe(doc, GROUPE_COPIES).addObject(copie)
        else:
            parent.addObject(copie)
    # Use the shape SAVED in the source file: no recompute, version independent.
    # The shape carries the placement of `src` (position inside its Part).
    copie.Shape = forme_propre(forme_source(src))
    copie.Label = 'Fige_' + src.Label if parent is None else src.Label
    _proprietes_figeage(copie, src, doc)
    try:
        # Hidden in Solides_figes (the Link displays it); inside a frozen
        # container visible like the source (a Link to a container only
        # shows its visible children)
        copie.Visibility = parent is not None and bool(src.Visibility)
    except Exception:
        pass
    if App.GuiUp:
        try:
            if hasattr(src, 'ViewObject') and src.ViewObject:
                copie.ViewObject.ShapeAppearance = src.ViewObject.ShapeAppearance
        except Exception:
            pass
    return copie


# --------------------------------------------------------------------------
#  FREEZE containers: Parts, assemblies, sub-assemblies, imported STEP groups
# --------------------------------------------------------------------------
# A container is frozen member by member into a container of the same kind
# (an Assembly gives an Assembly, with its joints; a Part, a STEP LinkGroup
# or a plain group give an App::Part). A member that is a Link (component
# of a sub-assembly, element of a STEP group) becomes a Link of the frozen
# container, same label and placement, to a frozen copy of its target; the
# copies of linked objects are shared and stored hidden in Solides_figes.
# The returned path mapping keeps the joint references going through the
# container valid.

MODES = ("structure", "block")


def _enfants_directs(part):
    """Children of an App::Part that are not consumed by a sibling (e.g. the
    tools of a boolean): the parts the user sees in the container."""
    groupe = list(part.Group)
    noms = set(c.Name for c in groupe)
    return [c for c in groupe
            if not any(p.Name in noms and p.Document is part.Document
                       for p in c.InList if p is not part)]


def _est_solide(o):
    try:
        return o.isDerivedFrom('Part::Feature') and not _est_lien(o) \
            and not o.Shape.isNull() and bool(o.Shape.Solids)
    except Exception:
        return False


def _chemins_origine(origine_src, origine_copie):
    """Path mapping of an App::Origin and its axes / planes, matched by Role."""
    if origine_src is None or origine_copie is None:
        return {}
    par_role = dict((f.Role, f.Name) for f in origine_copie.OriginFeatures)
    sous = dict((f.Name, (par_role[f.Role], None))
                for f in origine_src.OriginFeatures if f.Role in par_role)
    return {origine_src.Name: (origine_copie.Name, sous)}

# Member types that carry no geometry of their own (joints are copied apart)
_IGNORES = ('App::Origin', 'App::VarSet', 'Spreadsheet::Sheet', 'App::TextDocument')


def _est_groupe_source(o):
    """Containers whose members are frozen one by one."""
    if o is None or _est_assemblage_lien(o):
        return False
    return o.TypeId in ('App::LinkGroup', 'App::DocumentObjectGroup') or \
        o.isDerivedFrom('App::Part')


def _membres(src):
    """Members of a container: the ElementList of a STEP LinkGroup, the
    Group of a Part / assembly / group minus what a sibling consumes (tools
    of a boolean). Joints and members without geometry are left out FIRST:
    in an assembly the joints reference every component, which would then
    look consumed."""
    if src.TypeId == 'App::LinkGroup':
        return list(src.ElementList)
    groupe = [c for c in src.Group if not _ignore(c)]
    noms = set(c.Name for c in groupe)
    # same document only: a Link of another file may carry a sibling's name
    return [c for c in groupe
            if not any(p.Name in noms and p.Document is src.Document
                       for p in c.InList if p is not src)]


def _ignore(o):
    """Members without geometry of their own: origin, joints, assembly
    helper groups, spreadsheets, selection sets..."""
    if o.TypeId in _IGNORES:
        return True
    if o.TypeId.startswith('Assembly::') and not _est_assemblage_obj(o) and \
            not _est_assemblage_lien(o):
        return True                     # JointGroup, ViewGroup, BomGroup...
    props = o.PropertiesList
    if 'JointType' in props or 'ObjectToGround' in props or 'SelectionSetMembers' in props:
        return True
    return not (_est_lien(o) or _est_groupe_source(o) or _est_assemblage_lien(o)
                or o.isDerivedFrom('Part::Feature'))


def _forme_ok(o):
    try:
        return not o.Shape.isNull()
    except Exception:
        return False


def obstacles(src, profondeur=0):
    """Why `src` (target of a Link, or a member) cannot be frozen: a list of
    readable reasons, empty when everything inside can. Checked BEFORE any
    change, so that nothing is ever half frozen."""
    if profondeur > 30:
        return [tr("{name}: nesting too deep").format(name=src.Label)]
    if src is None:
        return [tr("missing target")]
    if _est_lien(src):
        if src.LinkedObject is None:
            return [tr("{name}: broken link (no target)").format(name=src.Label)]
        return obstacles(src.LinkedObject, profondeur + 1)
    if _est_assemblage_lien(src):
        if src.LinkedObject is None:
            return [tr("{name}: sub-assembly without its assembly").format(name=src.Label)]
        return obstacles(src.LinkedObject, profondeur + 1)
    if _est_groupe_source(src):
        out = []
        for m in _membres(src):
            if not _ignore(m):
                out += obstacles(m, profondeur + 1)
        return out
    if src.isDerivedFrom('Part::Feature'):
        return [] if not forme_source(src).isNull() else \
            [tr("{name}: empty shape").format(name=src.Label)]
    return [tr("{name}: type {type} not supported").format(name=src.Label, type=src.TypeId)]


def _copier_proprietes_lien(dst, src):
    """Placement, transform and array settings of a Link (or the Placement
    of a sub-assembly) onto the frozen Link."""
    for p in ('Placement', 'LinkTransform', 'ScaleVector', 'ElementCount', 'PlacementList',
              'ScaleList', 'VisibilityList'):
        if p in src.PropertiesList and p in dst.PropertiesList:
            try:
                setattr(dst, p, getattr(src, p))
            except Exception:
                pass
    try:
        dst.Visibility = src.Visibility
    except Exception:
        pass
    if App.GuiUp:                       # colour overrides (STEP import)
        try:
            vs, vd = src.ViewObject, dst.ViewObject
            for p in ('OverrideMaterial', 'ShapeMaterial', 'ShapeAppearance',
                      'OverrideMaterialList', 'MaterialList', 'OverrideColorList'):
                if vs is not None and vd is not None and p in vs.PropertiesList \
                        and p in vd.PropertiesList:
                    setattr(vd, p, getattr(vs, p))
        except Exception:
            pass


def _trouver_lien_fige(doc, src, parent):
    nom = os.path.basename(src.Document.FileName or '')
    for o in (parent.Group if parent is not None else doc.Objects):
        if _est_lien_fige(o) and o.FigeObjet == src.Name and \
                os.path.basename(o.FigeFichier) == nom and \
                o.getParentGeoFeatureGroup() is parent:
            return o
    return None


def _lien_fige(doc, src, cible, parent):
    """Frozen Link standing for the source Link / sub-assembly `src`, inside
    the frozen container `parent` (or shared and hidden in Solides_figes
    when parent is None), pointing to the frozen `cible`."""
    lk = _trouver_lien_fige(doc, src, parent)
    if lk is None:
        lk = doc.addObject('App::Link', 'Fige_' + src.Name)
        if parent is None:
            _groupe(doc, GROUPE_COPIES).addObject(lk)
        else:
            parent.addObject(lk)
    lk.LinkedObject = cible
    _copier_proprietes_lien(lk, src)
    lk.Label = src.Label if parent is not None else 'Fige_' + src.Label
    _proprietes_figeage(lk, src, doc)
    if parent is None:
        try:
            lk.Visibility = False
        except Exception:
            pass
    return lk


def _assemblage_lien_fige(doc, src, fa, parent):
    """Frozen sub-assembly standing for the nested sub-assembly `src`
    inside the frozen assembly `parent`: an Assembly::AssemblyLink to `fa`
    (same kind as the source, so that the sub-assemblies mirroring it in
    the main assembly can be pointed to it), or a frozen Link when the
    document is not saved yet (an AssemblyLink needs its file)."""
    if not doc.FileName:
        return _lien_fige(doc, src, fa, parent)
    nal = None
    for o in parent.Group:
        if _est_assemblage_lien_fige(o) and o.FigeObjet == src.Name:
            nal = o
    if nal is None:
        nal = doc.addObject('Assembly::AssemblyLink', 'Fige_' + src.Name)
        parent.addObject(nal)
    nal.Rigid = getattr(src, 'Rigid', True)
    if nal.LinkedObject is not fa:
        nal.LinkedObject = fa
    nal.Placement = src.Placement
    nal.Label = src.Label
    _proprietes_figeage(nal, src, doc)
    nal.recompute()                     # creates its children (needed for the paths)
    return nal


def copie_cible(doc, cible):
    """Frozen equivalent of the target of a Link: (frozen object, path
    mapping for the references going through it, None for a leaf)."""
    if _est_lien(cible):                # Link to a Link: keep the chain
        c, chemins = copie_cible(doc, cible.LinkedObject)
        return _lien_fige(doc, cible, c, None), chemins
    if _est_groupe_source(cible):
        return _creer_ou_rafraichir_conteneur(doc, cible)
    if cible.isDerivedFrom('Part::Feature'):
        return _creer_ou_rafraichir_copie(doc, cible), None
    raise RuntimeError(tr("{name}: type {type} not supported").format(
        name=cible.Label, type=cible.TypeId))


def _figer_membre(doc, m, cont):
    """Frozen equivalent of the member `m` inside the frozen container
    `cont`: (object, path mapping), or None for members without geometry."""
    if _ignore(m):
        return None
    if _est_assemblage_lien(m):
        # Nested sub-assembly: a sub-assembly of the frozen assembly (a Link
        # when this document has no file yet), pointing to the frozen copy
        # of its assembly; its children are mapped to the source children
        fa, ch = _creer_ou_rafraichir_conteneur(doc, m.LinkedObject)
        nal = _assemblage_lien_fige(doc, m, fa, cont)
        sous = {}
        if _est_lien(nal):
            for c in m.Group:
                t = c.LinkedObject if _est_lien(c) else None
                if t is not None and t.Name in ch:
                    sous[c.Name] = ch[t.Name]
        else:
            par_source = dict((getattr(c.LinkedObject, 'FigeObjet', None), c)
                              for c in nal.Group if getattr(c, 'LinkedObject', None) is not None)
            for c in m.Group:
                t = getattr(c, 'LinkedObject', None)
                if t is not None and t.Name in par_source:
                    sous[c.Name] = (par_source[t.Name].Name, None)
        return nal, sous
    if _est_lien(m):
        c, chemins = copie_cible(doc, m.LinkedObject)
        return _lien_fige(doc, m, c, cont), chemins
    if _est_groupe_source(m):
        return _creer_ou_rafraichir_conteneur(doc, m, cont)
    return _creer_ou_rafraichir_copie(doc, m, cont), None


def _creer_ou_rafraichir_conteneur(doc, src, parent=None):
    """Frozen copy of the container `src` (App::Part, Assembly, STEP
    LinkGroup, group), members frozen recursively. Returns (container, path
    mapping source name -> copy name) used to rewrite the joint references
    going through the container."""
    assemblage = _est_assemblage_obj(src)
    cont = _trouver_copie(doc, src, parent, test=_est_conteneur_fige)
    if cont is not None and _est_assemblage_obj(cont) != assemblage:
        _supprimer_fige(doc, cont)      # kind changed in the source
        cont = None
    if cont is None:
        cont = doc.addObject('Assembly::AssemblyObject' if assemblage else 'App::Part',
                             'Fige_' + src.Name)
        if parent is None:
            _groupe(doc, GROUPE_COPIES).addObject(cont)
        else:
            parent.addObject(cont)
    cont.Label = 'Fige_' + src.Label if parent is None else src.Label
    if 'Placement' in src.PropertiesList:
        cont.Placement = src.Placement  # matters for nested containers only
    _proprietes_figeage(cont, src, doc)

    chemins, gardes = {}, set()
    for m in _membres(src):
        r = _figer_membre(doc, m, cont)
        if r is None:
            continue
        c, sous = r
        chemins[m.Name] = (c.Name, sous)
        gardes.add(c.Name)
    chemins.update(_chemins_origine(getattr(src, 'Origin', None),
                                    getattr(cont, 'Origin', None)))
    # Copies of members removed from the source since the last freeze
    for o in list(cont.Group):
        if (_est_fige(o) or _est_lien_fige(o) or _est_assemblage_lien_fige(o)) and \
                o.Name not in gardes:
            _supprimer_fige(doc, o)
    if assemblage:
        _copier_liaisons(doc, src, cont, chemins)
    try:
        # Hidden at top level (the Link displays it), as the source when nested
        cont.Visibility = parent is not None and bool(getattr(src, 'Visibility', True))
    except Exception:
        pass
    return cont, chemins


def _copier_liaisons(doc, src, cont, chemins):
    """Joints and groundings of the source assembly, recreated in the frozen
    assembly on the frozen components (Assembly workbench API, as the
    duplication does). Joints that cannot be copied are reported, the
    frozen components keep their solved placement anyway."""
    try:
        import UtilsAssembly
        from . import duplicate
    except Exception as exc:
        App.Console.PrintWarning(tr("Freeze: joints of {name} not copied ({error}).").format(
            name=src.Label, error=exc) + "\n")
        return
    groupe = UtilsAssembly.getJointGroup(cont)
    for j in list(groupe.Group):        # refreshed from the source each time
        doc.removeObject(j.Name)
    sgroupe = None
    for o in src.Group:
        if o.TypeId == 'Assembly::JointGroup':
            sgroupe = o
    if sgroupe is None:
        return
    correspondance = {}
    for nom, (copie, _sous) in chemins.items():
        o_src, o_copie = src.Document.getObject(nom), doc.getObject(copie)
        if o_src is not None and o_copie is not None:
            correspondance[o_src] = o_copie
    perdues = []
    # A frozen assembly is a snapshot: whatever the Assembly workbench does
    # while the joints are recreated, every member gets its source placement
    # back afterwards
    places = dict((o.Name, o.Placement) for o in cont.Group if 'Placement' in o.PropertiesList)
    ordre = sorted(sgroupe.Group, key=lambda j: 'ObjectToGround' not in j.PropertiesList)
    for j in ordre:
        try:
            if duplicate.copy_joint_into(doc, j, correspondance, cont, chemins) is None:
                perdues.append(j.Label)
        except Exception as exc:
            perdues.append("%s (%s)" % (j.Label, exc))
    for o in cont.Group:
        if o.Name in places and o.Placement != places[o.Name]:
            o.Placement = places[o.Name]
    # The joints of a frozen copy are kept for the record, their markers
    # would only clutter the view of the main assembly
    for j in groupe.Group:
        try:
            j.Visibility = False
        except Exception:
            pass
    if perdues:
        App.Console.PrintWarning(tr("Freeze: {n} joint(s) of {name} not copied, its parts "
                                    "keep their placement: {joints}").format(
            n=len(perdues), name=src.Label, joints=", ".join(perdues)) + "\n")


# --------------------------------------------------------------------------
#  FREEZE as one block (one solid for a whole container)
# --------------------------------------------------------------------------

def _feuilles(src, chemin=(), profondeur=0):
    """Leaves of a container in display order: [(path of member names from
    src, label, file name)]; a leaf is a solid object, reached through
    Links and nested containers."""
    out = []
    if profondeur > 30:
        return out
    for m in _membres(src):
        if _ignore(m):
            continue
        p = chemin + (m.Name,)
        t = m
        while _est_lien(t) and t.LinkedObject is not None:
            t = t.LinkedObject
        if _est_assemblage_lien(m):
            for c in m.Group:
                if _est_lien(c) and c.LinkedObject is not None:
                    out += _feuilles_cible(c, p + (c.Name,), profondeur + 1)
        elif _est_groupe_source(t):
            out += _feuilles(t, p, profondeur + 1)
        elif t.isDerivedFrom('Part::Feature'):
            out.append((p, t.Label, os.path.basename(t.Document.FileName or '')))
    return out


def _feuilles_cible(lien, chemin, profondeur):
    t = lien
    while _est_lien(t) and t.LinkedObject is not None:
        t = t.LinkedObject
    if _est_groupe_source(t):
        return _feuilles(t, chemin, profondeur)
    if t.isDerivedFrom('Part::Feature'):
        return [(chemin, t.Label, os.path.basename(t.Document.FileName or ''))]
    return []


def _compter(shape):
    return len(shape.Faces), len(shape.Edges), len(shape.Vertexes)


def _creer_ou_rafraichir_bloc(doc, src):
    """Frozen copy of the whole container `src` as ONE Part::Feature (a
    compound of every leaf, in src coordinates). FigeBlocCarte keeps the
    path and the element counts of each leaf, to renumber the joint
    references; FigeNomenclature the parts it holds, for the BOM."""
    feuilles = _feuilles(src)
    formes, carte, nomenclature = [], [], []
    for chemin, label, fichier in feuilles:
        sh = Part.getShape(src, '.'.join(chemin) + '.', needSubElement=False, transform=False)
        if sh.isNull():
            # never a silent loss (a Body holding only a binder has no shape
            # of its own): the structure mode freezes such parts
            raise RuntimeError(tr("{name}: {part} has no shape of its own (e.g. a Body holding "
                                  "only a binder): freeze it with its structure.").format(
                name=src.Label, part=label))
        formes.append(sh)
        f, e, v = _compter(sh)
        carte.append("%s|%d|%d|%d" % ('.'.join(chemin), f, e, v))
        nomenclature.append("%s|%s" % (label, fichier))
    if not formes:
        raise RuntimeError(tr("{name}: nothing to freeze").format(name=src.Label))
    test = lambda o: _est_copie_figee(o) and 'FigeBlocCarte' in o.PropertiesList
    copie = _trouver_copie(doc, src, None, test=test)
    if copie is None:
        copie = doc.addObject('Part::Feature', 'Fige_' + src.Name)
        _groupe(doc, GROUPE_COPIES).addObject(copie)
        copie.addProperty('App::PropertyStringList', 'FigeBlocCarte', 'Figeage',
                          'path|faces|edges|vertices of each part of the block')
        copie.addProperty('App::PropertyStringList', 'FigeNomenclature', 'Figeage',
                          'label|file of each part of the block')
    copie.Shape = forme_propre(Part.makeCompound(formes))
    copie.FigeBlocCarte = carte
    copie.FigeNomenclature = nomenclature
    copie.Label = 'Fige_' + src.Label
    _proprietes_figeage(copie, src, doc)
    try:
        copie.Visibility = False
    except Exception:
        pass
    return copie


def lire_carte(copie):
    """[(path tuple, faces, edges, vertices)] of a frozen block."""
    out = []
    for ligne in getattr(copie, 'FigeBlocCarte', []) or []:
        chemin, f, e, v = ligne.rsplit('|', 3)
        out.append((tuple(chemin.split('.')), int(f), int(e), int(v)))
    return out


def renumeroter_vers_bloc(sub, k, carte):
    """Subname through a Link to a container -> subname on the frozen block:
    the leaf is found by its path, the element shifted by the elements of
    the leaves before it ('Sub.Bolt001.Face3' -> 'Face27'). Unknown paths
    are kept (the diagnostic then shows the broken reference)."""
    objets, _mapped, elem = decouper_sub(sub)
    reste = tuple(objets[k + 1:])
    prefixe = '.'.join(objets[:k + 1])
    prefixe = prefixe + '.' if prefixe else ''
    m = _RE_ELEM_NUM.match(elem or '')
    if not m:
        return sub
    genre, n = m.group(1), int(m.group(2))
    decalage = {'Face': 0, 'Edge': 0, 'Vertex': 0}
    for chemin, f, e, v in carte:
        if reste[:len(chemin)] == chemin:
            return "%s%s%d" % (prefixe, genre, decalage[genre] + n)
        decalage['Face'] += f
        decalage['Edge'] += e
        decalage['Vertex'] += v
    return sub


def renumeroter_depuis_bloc(sub, k, carte):
    """Inverse of renumeroter_vers_bloc, to relink a block to its source."""
    objets, _mapped, elem = decouper_sub(sub)
    prefixe = '.'.join(objets[:k + 1])
    prefixe = prefixe + '.' if prefixe else ''
    m = _RE_ELEM_NUM.match(elem or '')
    if not m:
        return sub
    genre, n = m.group(1), int(m.group(2))
    rang = {'Face': 1, 'Edge': 2, 'Vertex': 3}[genre]
    for ligne in carte:
        compte = ligne[rang]
        if n <= compte:
            return "%s%s.%s%d" % (prefixe, '.'.join(ligne[0]), genre, n)
        n -= compte
    return sub


def _supprimer_fige(doc, o):
    if _est_assemblage_lien(o):
        for c in list(o.Group):
            if _est_assemblage_lien(c):
                _supprimer_fige(doc, c)
            else:
                doc.removeObject(c.Name)
    if _est_conteneur_fige(o):
        for c in list(o.Group):
            if _est_fige(c) or _est_lien_fige(c) or _est_assemblage_lien_fige(c):
                _supprimer_fige(doc, c)
            elif c.TypeId == 'Assembly::JointGroup':
                for j in list(c.Group):
                    doc.removeObject(j.Name)
                doc.removeObject(c.Name)
    App.Console.PrintMessage(
        tr("Freeze: obsolete copy removed: {name}").format(name=o.Label) + "\n")
    doc.removeObject(o.Name)


# --------------------------------------------------------------------------
#  UNUSED FROZEN COPIES
# --------------------------------------------------------------------------

def _marque(obj, inutile):
    """Show / remove the "suppressed" overlay icon of the tree on `obj`
    (App / Gui SuppressibleExtension, FreeCAD 1.1+). The extensions are only
    added to objects that need the mark; without them nothing is shown but
    the sub-group still sorts the copies."""
    if "Suppressed" not in obj.PropertiesList:
        if not inutile:
            return
        try:
            obj.addExtension("App::SuppressibleExtensionPython")
            if App.GuiUp and obj.ViewObject is not None:
                obj.ViewObject.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        except Exception:
            return
    try:
        if obj.Suppressed != inutile:
            obj.Suppressed = inutile
    except Exception:
        pass


def copies_inutilisees(doc):
    """Top-level frozen copies / containers no Link of `doc` uses (read only)."""
    copies = [o for o in doc.Objects if (_est_fige(o) or _est_lien_fige(o))
              and o.getParentGeoFeatureGroup() is None]
    utilisees = _cibles_utilisees(doc)
    return [c for c in copies if c.Name not in utilisees]


def _cibles_utilisees(doc):
    """Names of the objects some Link or sub-assembly of `doc` points to."""
    return set(l.LinkedObject.Name for l in doc.Objects
               if (_est_lien(l) or _est_assemblage_lien(l)) and l.LinkedObject is not None)


def marquer_inutilisees(doc):
    """Frozen copies / containers that no Link of `doc` uses any more (part
    deleted, relinked, replaced...) are moved into the sub-group "Unused" of
    Solides_figes and get the overlay icon, so they can be sorted out by
    hand; copies used again go back. Returns the unused ones."""
    copies = [o for o in doc.Objects if (_est_fige(o) or _est_lien_fige(o))
              and o.getParentGeoFeatureGroup() is None]     # not inside a container
    if not copies:
        return []
    utilisees = _cibles_utilisees(doc)
    inutiles = [c for c in copies if c.Name not in utilisees]
    principal = doc.getObject(GROUPE_COPIES)
    sous = doc.getObject(GROUPE_INUTILES)
    if inutiles and sous is None and principal is not None:
        sous = doc.addObject('App::DocumentObjectGroup', GROUPE_INUTILES)
        sous.Label = tr("Unused")
        principal.addObject(sous)
    for c in copies:
        inutile = c in inutiles
        if inutile and sous is not None and c not in sous.Group:
            sous.addObject(c)               # also removes it from Solides_figes
        elif not inutile and sous is not None and c in sous.Group and principal is not None:
            principal.addObject(c)
        _marque(c, inutile)
    if sous is not None and not sous.Group:
        doc.removeObject(sous.Name)
    return inutiles


def _chemins_inverses(cont, src):
    """Path mapping copy name -> source name, to relink a frozen container
    to its source (inverse of _creer_ou_rafraichir_conteneur)."""
    chemins = {}
    for c in cont.Group:
        o = src.Document.getObject(c.FigeObjet) if (_est_fige(c) or _est_lien_fige(c)) \
            else None
        if o is None:
            continue
        if _est_conteneur_fige(c):
            chemins[c.Name] = (o.Name, _chemins_inverses(c, o))
        elif _est_lien_fige(c):
            chemins[c.Name] = (o.Name, _inverse_lien(c, o))
        else:
            chemins[c.Name] = (o.Name, None)
    chemins.update(_chemins_origine(getattr(cont, 'Origin', None),
                                    getattr(src, 'Origin', None)))
    return chemins


def _inverse_lien(lk, o):
    """Path mapping below a frozen Link `lk` back to its source member `o`."""
    cible = lk.LinkedObject
    while _est_lien_fige(cible) and cible.getParentGeoFeatureGroup() is None \
            and _est_lien(cible.LinkedObject):
        cible = cible.LinkedObject
    if _est_assemblage_lien(o):
        # frozen components -> children of the source sub-assembly
        sous = {}
        for c in o.Group:
            t = c.LinkedObject if _est_lien(c) else None
            for fc in (cible.Group if _est_conteneur_fige(cible) else []):
                if t is not None and getattr(fc, 'FigeObjet', None) == t.Name:
                    sous[fc.Name] = (c.Name, None)
        return sous
    t = o.LinkedObject if _est_lien(o) else None
    while _est_lien(t):
        t = t.LinkedObject
    if _est_conteneur_fige(cible) and t is not None:
        return _chemins_inverses(cible, t)
    return None


def _figer_un(doc, lien, mode):
    """Freeze one Link or sub-assembly. Returns the number of references
    rewritten."""
    src = lien.LinkedObject
    if _est_assemblage_lien(lien):
        return _figer_assemblage_lien(doc, lien, mode)
    if mode == "block" and _est_groupe_source(src):
        copie = _creer_ou_rafraichir_bloc(doc, src)
        carte = lire_carte(copie)
        return appliquer_reecriture(lien, nouvelle_cible=copie,
                                    fonction=lambda sub, k: renumeroter_vers_bloc(sub, k, carte))
    copie, chemins = copie_cible(doc, src)
    return appliquer_reecriture(lien, nouvelle_cible=copie, chemins=chemins)


def _figer_assemblage_lien(doc, al, mode):
    """Sub-assembly of FreeCAD 26.x (Assembly::AssemblyLink): its assembly is
    frozen into an Assembly of this document, the children of `al` (and of
    the nested sub-assemblies it mirrors) are pointed to the matching frozen
    members, same names: the joints of the main assembly stay valid."""
    if mode == "block":
        App.Console.PrintWarning(tr("Freeze: {name} is a sub-assembly of the Assembly "
                                    "workbench; it is frozen with its structure (one block "
                                    "is only possible for a Link).").format(name=al.Label)
                                 + "\n")
    fa, _chemins = _creer_ou_rafraichir_conteneur(doc, al.LinkedObject)
    touches = _recibler(al, fa, lambda m, t: m.FigeObjet == t.Name)
    al.LinkedObject = fa
    return sum(appliquer_reecriture(c) for c in touches)


def _membres_cibles(asm):
    return [m for m in asm.Group if _est_fige(m) or _est_lien_fige(m) or
            _est_assemblage_lien(m) or _est_lien(m)]


def _recibler(al, cible, correspond):
    """Point each child of the sub-assembly `al` to the member of the
    assembly `cible` matching its current target (correspond(member,
    target)); nested sub-assemblies recursively. Returns the child Links
    retargeted (their references must be rewritten)."""
    touches = []
    membres = _membres_cibles(cible)
    for c in list(al.Group):
        t = getattr(c, 'LinkedObject', None)
        if t is None or not (_est_lien(c) or _est_assemblage_lien(c)):
            continue
        m = None
        for x in membres:
            try:
                if correspond(x, t):
                    m = x
            except Exception:
                pass
        if m is None:
            continue
        if _est_assemblage_lien(c) and _est_assemblage_lien(m):
            touches += _recibler(c, m.LinkedObject, correspond)
        c.LinkedObject = m
        if _est_lien(c):
            touches.append(c)
    return touches


def figer(doc=None, selection=None, mode="structure"):
    """Freeze the given Links / sub-assemblies (selection) or every external
    one (None). mode = "structure" (default: containers and sub-assemblies
    keep their parts, names, placements and joints) or "block" (a Link to a
    container becomes ONE frozen solid). A Link whose content cannot be
    frozen is left linked and reported; any error undoes the whole freeze
    (one transaction). Returns {"frozen": [names], "skipped": [{"name",
    "reason"}], "refs_updated": n}."""
    doc = doc or App.ActiveDocument
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))
    result = {"frozen": [], "skipped": [], "refs_updated": 0}
    liens = liens_externes(doc, selection)
    if not liens:
        App.Console.PrintMessage(tr("Freeze: no external link to freeze.") + "\n")
        return result
    a_figer = []
    for lien in liens:
        raisons = obstacles(lien.LinkedObject)
        if raisons:
            App.Console.PrintWarning(
                tr("Freeze: {link} is left linked: {reasons}").format(
                    link=lien.Label, reasons="; ".join(raisons)) + "\n")
            result["skipped"].append({"name": lien.Name, "reason": "; ".join(raisons)})
        else:
            a_figer.append(lien)
    if not a_figer:
        return result
    doc.openTransaction(tr("Freeze components"))
    try:
        for lien in a_figer:
            n = _figer_un(doc, lien, mode)
            App.Console.PrintMessage(
                tr("Freeze: {name} frozen ({n} references refreshed)").format(
                    name=lien.Label, n=n) + "\n")
            result["frozen"].append(lien.Name)
            result["refs_updated"] += n
        marquer_inutilisees(doc)
        doc.recompute()
    except Exception:
        doc.abortTransaction()          # never a half-frozen assembly
        raise
    doc.commitTransaction()
    return result


# --------------------------------------------------------------------------
#  RELINK (back to the source file)
# --------------------------------------------------------------------------

def _relier_un(doc, lien, copie, src):
    if _est_assemblage_lien(lien):
        # frozen member -> source member of the same name
        touches = _recibler(lien, src, lambda m, t: getattr(t, 'FigeObjet', None) == m.Name)
        lien.LinkedObject = src
        return sum(appliquer_reecriture(c) for c in touches)
    if 'FigeBlocCarte' in copie.PropertiesList:
        carte = lire_carte(copie)
        return appliquer_reecriture(
            lien, nouvelle_cible=src,
            fonction=lambda sub, k: renumeroter_depuis_bloc(sub, k, carte))
    if _est_conteneur_fige(copie):
        return appliquer_reecriture(lien, nouvelle_cible=src,
                                    chemins=_chemins_inverses(copie, src))
    # "Face6" stays valid on a Body; flush hidden names of the copy
    return appliquer_reecriture(lien, nouvelle_cible=src)


def relier(doc=None, selection=None):
    """Point the given frozen Links / sub-assemblies (selection) or all of
    them (None) back to their source. The frozen copy is kept and reused on
    next freeze."""
    doc = doc or App.ActiveDocument
    result = {"relinked": [], "missing_source": []}
    liens = liens_figes(doc, selection)
    if not liens:
        App.Console.PrintMessage(tr("Freeze: no frozen link.") + "\n")
        return result
    doc.openTransaction(tr("Relink to sources"))
    try:
        for lien in liens:
            copie = lien.LinkedObject
            doc_src, _ = _ouvrir_source(copie, doc)
            src = _objet_source(copie, doc_src) if doc_src else None
            if src is None:
                App.Console.PrintError(
                    tr("Freeze: source not found for {name} ({file})").format(
                        name=lien.Label, file=copie.FigeFichier) + "\n")
                result["missing_source"].append({"name": lien.Name, "file": copie.FigeFichier})
                continue
            _relier_un(doc, lien, copie, src)
            App.Console.PrintMessage(
                tr("Freeze: {name} relinked to {doc}#{obj}").format(
                    name=lien.Label, doc=doc_src.Name, obj=src.Name) + "\n")
            result["relinked"].append(lien.Name)
        marquer_inutilisees(doc)
        doc.recompute()
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    return result


# --------------------------------------------------------------------------
#  SELECTION
# --------------------------------------------------------------------------

def _lien_utile(o, doc):
    """Assembly Link pointing to an external Body / Part or to a frozen copy."""
    if not _est_lien(o) or o.Document is not doc or o.LinkedObject is None:
        return False
    return o.LinkedObject.Document is not doc or _est_fige(o.LinkedObject)


def selection_liens():
    """Links targeted by the current selection (tree or 3D view).
    - nothing selected               -> None (= whole document)
    - a Link / a face of a part      -> that Link
    - a frozen copy or container
      (Solides_figes)                -> every Link using it
    - unrelated selection            -> []   (= nothing, never the whole doc)"""
    if not App.GuiUp:
        return None
    import FreeCADGui as Gui
    doc = App.ActiveDocument
    selex = Gui.Selection.getSelectionEx('', 0)   # 0 = do not resolve Links
    if not selex:
        return None
    liens = []

    def ajouter(o):
        if o not in liens:
            liens.append(o)

    for sel in selex:
        top = sel.Object
        for sub in (sel.SubElementNames or ('',)):
            try:
                chaine = top.getSubObjectList(sub) if sub else [top]
            except Exception:
                chaine = [top]
            utiles = [o for o in chaine if _lien_utile(o, doc)]
            if utiles:
                ajouter(utiles[-1])                  # Link closest to the part
                continue
            for o in chaine:
                if _est_fige(o):                     # frozen copy selected
                    # A copy inside a frozen container: the Links use the
                    # outermost container
                    cible = _conteneur_racine(o) or o
                    for l in doc.Objects:
                        if _est_lien(l) and l.LinkedObject is cible:
                            ajouter(l)
    if not liens:
        App.Console.PrintWarning(
            tr("Freeze: the selection holds no assembly part (Link). "
               "Nothing was done.") + "\n")
    return liens


# --------------------------------------------------------------------------
#  DELETE ALL JOINTS OF A PART
# --------------------------------------------------------------------------

def _est_assemblage(o):
    return o is not None and o.isDerivedFrom('Assembly::AssemblyObject')


def selection_composants():
    """Selected assembly parts (direct child of an Assembly, Link or not).
    A selected frozen copy -> every part using it."""
    if not App.GuiUp:
        return []
    import FreeCADGui as Gui
    doc = App.ActiveDocument
    comps = []

    def ajouter(o):
        if o not in comps:
            comps.append(o)

    for sel in Gui.Selection.getSelectionEx('', 0):
        top = sel.Object
        for sub in (sel.SubElementNames or ('',)):
            try:
                chaine = top.getSubObjectList(sub) if sub else [top]
            except Exception:
                chaine = [top]
            # The part is the object right below the deepest Assembly
            idx = [i for i, o in enumerate(chaine) if _est_assemblage(o)]
            if idx and idx[-1] + 1 < len(chaine):
                ajouter(chaine[idx[-1] + 1])
                continue
            if not sub and any(_est_assemblage(p) for p in top.InList):
                ajouter(top)
                continue
            for o in chaine:
                if _est_copie_figee(o):
                    for l in doc.Objects:
                        if _est_lien(l) and l.LinkedObject is o:
                            ajouter(l)
    return comps


def liaisons_de(comp):
    """Joints (and 'Grounded' fixation) using the part `comp`."""
    res = []
    for o, _p, _t, _i, _j, _k, _s in references_via(comp):
        if hasattr(o, 'JointType') and o not in res:
            res.append(o)
    for o in comp.InList:
        if getattr(o, 'ObjectToGround', None) is comp and o not in res:
            res.append(o)
    return res


def supprimer_liaisons(comps, confirmer=True):
    """Delete every joint of the given parts, after confirmation.
    Undoable in one step. Returns the number of deleted joints."""
    if not comps:
        App.Console.PrintWarning(
            tr("Freeze: select one or more parts of the assembly.") + "\n")
        return 0
    doc = comps[0].Document
    a_suppr = []
    for c in comps:
        for j in liaisons_de(c):
            if j not in a_suppr:
                a_suppr.append(j)
    if not a_suppr:
        App.Console.PrintMessage(
            tr("Freeze: no joint on {names}.").format(
                names=', '.join(c.Label for c in comps)) + "\n")
        return 0
    if confirmer and App.GuiUp:
        from PySide import QtGui
        try:
            from PySide import QtWidgets
        except ImportError:
            QtWidgets = QtGui
        texte = tr("Delete {n} joint(s) of: {names}?\n\n{joints}").format(
            n=len(a_suppr), names=', '.join(c.Label for c in comps),
            joints='\n'.join('  - ' + j.Label for j in a_suppr[:30]) +
            ('\n  ...' if len(a_suppr) > 30 else ''))
        r = QtWidgets.QMessageBox.question(None, tr("Delete joints"), texte,
                                           QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if r != QtWidgets.QMessageBox.Yes:
            return 0
    doc.openTransaction(tr("Delete joints"))
    try:
        for j in a_suppr:
            App.Console.PrintMessage(
                tr("Freeze: joint deleted: {name}").format(name=j.Label) + "\n")
            doc.removeObject(j.Name)
        doc.recompute()
    finally:
        doc.commitTransaction()
    return len(a_suppr)


# --------------------------------------------------------------------------
#  DIAGNOSTIC / REPAIR
# --------------------------------------------------------------------------

def _taille_map(shape):
    try:
        return shape.ElementMapSize
    except Exception:
        return '?'


def _reference_ok(base, sub):
    """True when the reference resolves: the object path exists AND, for an
    element (Face6...), that element exists on it (getSubObject alone also
    returns the object for an element number out of range)."""
    if base is None or '?' in sub:          # '?' = element FreeCAD could not find
        return False
    try:
        if base.getSubObject(sub) is None:
            return False
        if decouper_sub(sub)[2]:
            shape = Part.getShape(base, sub, needSubElement=True)
            return not shape.isNull()
        return True
    except Exception:
        return False


def diagnostic_rows(doc):
    """Joint references of `doc` as data, without changing the document:
    [{"joint", "joint_label", "ref", "sub", "ok", "base", "base_file",
      "target", "target_file"}]."""
    rows = []
    for o in doc.Objects:
        if not hasattr(o, 'JointType'):
            continue
        for p in ('Reference1', 'Reference2'):
            v = getattr(o, p, None)
            if not v:
                continue
            base, subs = v
            for sub in ([subs] if isinstance(subs, str) else subs):
                ok = _reference_ok(base, sub)
                cible = getattr(base, 'LinkedObject', None) if base is not None else None
                rows.append({
                    "joint": o.Name, "joint_label": o.Label, "ref": p, "sub": sub,
                    "ok": bool(ok),
                    "base": base.Label if base is not None else None,
                    "base_type": base.TypeId if base is not None else None,
                    "base_file": base.Document.Label if base is not None else None,
                    "target": cible.Label if cible is not None else None,
                    "target_type": cible.TypeId if cible is not None else None,
                    "target_file": cible.Document.Label if cible is not None else None,
                })
    return rows


def diagnostic(doc=None):
    """Print, in the report view, the topological history size of each frozen
    copy (must be 0) and whether each joint reference resolves, with the
    object and file it is attached to. Returns the number of broken refs."""
    doc = doc or App.ActiveDocument
    pr = App.Console.PrintMessage
    pr(tr("===== Freeze diagnostic v{version}: {doc} (FreeCAD {fc}) =====").format(
        version=VERSION, doc=doc.Label, fc=_version_fc()) + "\n")
    for c in doc.Objects:
        if _est_copie_figee(c):
            pr(tr("Copy {label:<30} topological history = {size}  (must be 0)").format(
                label=c.Label, size=_taille_map(c.Shape)) + "\n")
    n_ok = n_ko = 0
    for r in diagnostic_rows(doc):
        ok = r["ok"]
        n_ok, n_ko = (n_ok + 1, n_ko) if ok else (n_ok, n_ko + 1)
        if r["base"] is None:
            desc = tr("no object")
        else:
            desc = tr("{label} ({type}, file {file})").format(
                label=r["base"], type=r["base_type"], file=r["base_file"])
            if r["target"] is not None:
                desc += ' -> ' + tr("{label} ({type}, file {file})").format(
                    label=r["target"], type=r["target_type"], file=r["target_file"])
        (pr if ok else App.Console.PrintError)(
            "  " + tr("{status} {joint:<12} {ref}: {sub:<10} on {target}").format(
                status=tr("OK") if ok else tr("KO"), joint=r["joint_label"], ref=r["ref"],
                sub=r["sub"], target=desc) + "\n")
    inutiles = marquer_inutilisees(doc)
    if inutiles:
        App.Console.PrintWarning(tr("Frozen copies used by no part (sub-group “Unused”, "
                                    "can be deleted): {names}").format(
            names=", ".join(c.Label for c in inutiles)) + "\n")
    pr(tr("===== {ok} reference(s) OK, {broken} broken =====").format(
        ok=n_ok, broken=n_ko) + "\n")
    return n_ko


def reparer(doc=None):
    """Clean existing frozen copies (remove topological history) and rewrite
    their references (also strips '?' markers). Meant for assemblies frozen
    with early versions of this module."""
    doc = doc or App.ActiveDocument
    doc.openTransaction(tr("Repair frozen copies"))
    try:
        for c in [o for o in doc.Objects if _est_copie_figee(o)]:
            c.Shape = forme_propre(c.Shape)
            for l in doc.Objects:
                if _est_lien(l) and l.LinkedObject is c:
                    appliquer_reecriture(l)
            App.Console.PrintMessage(
                tr("Freeze: copy cleaned: {name}").format(name=c.Label) + "\n")
        marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()
