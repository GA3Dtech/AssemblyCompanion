# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
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
    """Links pointing to another document (candidates for freezing)."""
    objs = doc.Objects if selection is None else selection
    return [o for o in objs if _est_lien(o) and o.LinkedObject is not None
            and o.LinkedObject.Document is not doc]


def liens_figes(doc, selection=None):
    """Links pointing to a frozen copy or container (candidates for relinking)."""
    objs = doc.Objects if selection is None else selection
    return [o for o in objs if _est_lien(o) and _est_fige(o.LinkedObject)]


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


def appliquer_reecriture(lien, remap=None, nouvelle_cible=None, chemins=None):
    """Rewrite every reference going through `lien`, after optionally
    retargeting the Link. With `chemins` (Link to an App::Part container),
    the path inside the target is translated instead of dropped. Each reference is CLEARED then written again, even
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
            refs[i][1][j] = (reecrire_sub_chemins(sub, k, chemins) if chemins is not None
                             else reecrire_sub(sub, k, remap))
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
    copie.Shape = forme_propre(src.Shape)
    copie.Label = 'Fige_' + src.Label
    _proprietes_figeage(copie, src, doc)
    if App.GuiUp:
        try:
            copie.ViewObject.Visibility = parent is not None
            if hasattr(src, 'ViewObject') and src.ViewObject:
                copie.ViewObject.ShapeAppearance = src.ViewObject.ShapeAppearance
        except Exception:
            pass
    return copie


# --------------------------------------------------------------------------
#  FREEZE an App::Part container
# --------------------------------------------------------------------------

def _enfants_directs(part):
    """Children of an App::Part that are not consumed by a sibling (e.g. the
    tools of a boolean): the parts the user sees in the container."""
    groupe = list(part.Group)
    noms = set(c.Name for c in groupe)
    return [c for c in groupe
            if not any(p.Name in noms for p in c.InList if p is not part)]


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


def _creer_ou_rafraichir_conteneur(doc, src, parent=None):
    """Frozen copy of the App::Part `src`: an App::Part holding a frozen copy
    of each Body / solid at its place (nested Parts are frozen recursively).
    Returns (container, path mapping source name -> copy name) used to
    rewrite the joint references going through the container."""
    cont = _trouver_copie(doc, src, parent, test=_est_conteneur_fige)
    if cont is None:
        cont = doc.addObject('App::Part', 'Fige_' + src.Name)
        if parent is None:
            _groupe(doc, GROUPE_COPIES).addObject(cont)
        else:
            parent.addObject(cont)
    cont.Label = 'Fige_' + src.Label
    cont.Placement = src.Placement      # matters for nested Parts only
    _proprietes_figeage(cont, src, doc)

    chemins, gardes = {}, set()
    for enfant in _enfants_directs(src):
        if enfant.isDerivedFrom('App::Part'):
            c, sous = _creer_ou_rafraichir_conteneur(doc, enfant, cont)
            chemins[enfant.Name] = (c.Name, sous)
        elif _est_solide(enfant):           # Body, Part::Feature, fasteners...
            c = _creer_ou_rafraichir_copie(doc, enfant, cont)
            chemins[enfant.Name] = (c.Name, None)
        else:
            if not enfant.isDerivedFrom('App::Origin'):
                App.Console.PrintWarning(
                    tr("Freeze: {part} / {child} ({type}) skipped in the container: only "
                       "Bodies, solids and nested Parts are frozen.").format(
                        part=src.Label, child=enfant.Label, type=enfant.TypeId) + "\n")
            continue
        gardes.add(c.Name)
    chemins.update(_chemins_origine(getattr(src, 'Origin', None),
                                    getattr(cont, 'Origin', None)))
    # Copies of objects removed from the source since the last freeze
    for o in list(cont.Group):
        if _est_fige(o) and o.Name not in gardes:
            _supprimer_fige(doc, o)
    if App.GuiUp:
        try:
            # Hidden at top level (the Link displays it), visible when nested
            cont.ViewObject.Visibility = parent is not None
        except Exception:
            pass
    return cont, chemins


def _supprimer_fige(doc, o):
    if _est_conteneur_fige(o):
        for c in list(o.Group):
            if _est_fige(c):
                _supprimer_fige(doc, c)
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


def marquer_inutilisees(doc):
    """Frozen copies / containers that no Link of `doc` uses any more (part
    deleted, relinked, replaced...) are moved into the sub-group "Unused" of
    Solides_figes and get the overlay icon, so they can be sorted out by
    hand; copies used again go back. Returns the unused ones."""
    copies = [o for o in doc.Objects if _est_fige(o)
              and o.getParentGeoFeatureGroup() is None]     # not inside a container
    if not copies:
        return []
    utilisees = set()
    for l in doc.Objects:
        if _est_lien(l) and l.LinkedObject is not None:
            utilisees.add(l.LinkedObject.Name)
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
    to its source App::Part (inverse of _creer_ou_rafraichir_conteneur)."""
    chemins = {}
    for c in cont.Group:
        o = src.Document.getObject(c.FigeObjet) if _est_fige(c) else None
        if o is None:
            continue
        if _est_conteneur_fige(c):
            chemins[c.Name] = (o.Name, _chemins_inverses(c, o))
        else:
            chemins[c.Name] = (o.Name, None)
    chemins.update(_chemins_origine(getattr(cont, 'Origin', None),
                                    getattr(src, 'Origin', None)))
    return chemins


def figer(doc=None, selection=None):
    """Freeze the given Links (selection) or every external Link (None)."""
    doc = doc or App.ActiveDocument
    liens = liens_externes(doc, selection)
    if not liens:
        App.Console.PrintMessage(tr("Freeze: no external link to freeze.") + "\n")
        return
    doc.openTransaction(tr("Freeze components"))
    try:
        for lien in liens:
            src = lien.LinkedObject
            if src.isDerivedFrom('App::Part'):
                copie, chemins = _creer_ou_rafraichir_conteneur(doc, src)
                n = appliquer_reecriture(lien, nouvelle_cible=copie, chemins=chemins)
            elif src.isDerivedFrom('Part::Feature'):
                copie = _creer_ou_rafraichir_copie(doc, src)
                n = appliquer_reecriture(lien, nouvelle_cible=copie)
            else:
                App.Console.PrintWarning(
                    tr("Freeze: {link} -> {target} ({type}) skipped: only Bodies, "
                       "Part::Features and Parts are supported.").format(
                        link=lien.Label, target=src.Label, type=src.TypeId) + "\n")
                continue
            App.Console.PrintMessage(
                tr("Freeze: {name} frozen ({n} references refreshed)").format(
                    name=lien.Label, n=n) + "\n")
        marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()


# --------------------------------------------------------------------------
#  RELINK (back to the source file)
# --------------------------------------------------------------------------

def relier(doc=None, selection=None):
    """Point the given frozen Links (selection) or all of them (None) back to
    their source Body. The frozen copy is kept and reused on next freeze."""
    doc = doc or App.ActiveDocument
    liens = liens_figes(doc, selection)
    if not liens:
        App.Console.PrintMessage(tr("Freeze: no frozen link.") + "\n")
        return
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
                continue
            if _est_conteneur_fige(copie):
                appliquer_reecriture(lien, nouvelle_cible=src,
                                     chemins=_chemins_inverses(copie, src))
            else:
                # "Face6" stays valid on a Body; flush hidden names of the copy
                appliquer_reecriture(lien, nouvelle_cible=src)
            App.Console.PrintMessage(
                tr("Freeze: {name} relinked to {doc}#{obj}").format(
                    name=lien.Label, doc=doc_src.Name, obj=src.Name) + "\n")
        marquer_inutilisees(doc)
        doc.recompute()
    finally:
        doc.commitTransaction()


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
    for o in doc.Objects:
        if not hasattr(o, 'JointType'):
            continue
        for p in ('Reference1', 'Reference2'):
            v = getattr(o, p, None)
            if not v:
                continue
            base, subs = v
            for sub in ([subs] if isinstance(subs, str) else subs):
                try:
                    # '?' = element FreeCAD could not find: always broken
                    ok = base is not None and '?' not in sub and \
                        base.getSubObject(sub) is not None
                except Exception:
                    ok = False
                n_ok, n_ko = (n_ok + 1, n_ko) if ok else (n_ok, n_ko + 1)
                if base is None:
                    desc = tr("no object")
                else:
                    cible = getattr(base, 'LinkedObject', None)
                    desc = tr("{label} ({type}, file {file})").format(
                        label=base.Label, type=base.TypeId, file=base.Document.Label)
                    if cible is not None:
                        desc += ' -> ' + tr("{label} ({type}, file {file})").format(
                            label=cible.Label, type=cible.TypeId, file=cible.Document.Label)
                (pr if ok else App.Console.PrintError)(
                    "  " + tr("{status} {joint:<12} {ref}: {sub:<10} on {target}").format(
                        status=tr("OK") if ok else tr("KO"), joint=o.Label, ref=p,
                        sub=sub, target=desc) + "\n")
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
