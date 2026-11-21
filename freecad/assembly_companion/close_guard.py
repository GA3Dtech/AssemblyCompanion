# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - warning when a source file of an assembly is closed
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
close_guard.py (Assembly Companion) - when a file is closed while parts of
an open assembly are still LINKED to it (not frozen), those parts silently
vanish from the assembly. Closing source files is precisely what one does
to tidy up the model tree, so in a hybrid assembly (old parts frozen, new
ones linked) it is an easy trap.

A document observer keeps track of the document every Link points into
(FreeCAD detaches the Links BEFORE it emits slotDeletedDocument, so they
cannot be looked up at that time). When a document is closed, the Links
that pointed into it and are now broken are the parts that vanished. Once the closing is over (deferred
with a timer: documents must not be changed inside the closing signal), a
dialog lists those parts and offers to:
  * freeze them: the file is reopened in the background, the Links find
    their target again, they are frozen, then the file is closed again;
  * reopen the file;
  * ignore.

Can be turned off with the preference WarnOnSourceClose.

The same observer keeps the "unused" mark of frozen copies up to date
(freeze.marquer_inutilisees) when a part is deleted or after undo / redo.

User-facing texts are in English, translated through i18n.tr().
"""

import FreeCAD as App

from . import prefs
from .i18n import tr

_observer = None


def _dependents(closing):
    """{assembly document name: [Link names]} of the Links of other open
    documents pointing into `closing` (frozen parts point into their own
    document, so they are not listed)."""
    out = {}
    for d in App.listDocuments().values():
        if d is closing:
            continue
        for o in d.Objects:
            try:
                if o.isDerivedFrom("App::Link") and o.LinkedObject is not None \
                        and o.LinkedObject.Document is closing:
                    out.setdefault(d.Name, []).append(o.Name)
            except Exception:
                pass
    return out


def _qt():
    try:
        from PySide import QtWidgets, QtCore
    except ImportError:
        from PySide6 import QtWidgets, QtCore
    return QtWidgets, QtCore


def _after_close(path, label, deps):
    """Runs once the document is closed: ask what to do."""
    import FreeCADGui as Gui
    from . import docs
    QtWidgets, _QtCore = _qt()
    # Still open? (when FreeCAD quits, the assemblies are closed too) and
    # really broken now that the file is gone
    deps = {name: [n for n in links if App.getDocument(name).getObject(n) is not None
                   and App.getDocument(name).getObject(n).LinkedObject is None]
            for name, links in deps.items() if name in App.listDocuments()}
    deps = {name: links for name, links in deps.items() if links}
    if not deps or not path:
        return
    lines = []
    for name, links in deps.items():
        d = App.getDocument(name)
        labels = [d.getObject(n).Label for n in links if d.getObject(n) is not None]
        lines.append("{asm}: {parts}".format(asm=d.Label, parts=", ".join(labels[:15])
                                             + (" …" if len(labels) > 15 else "")))
    count = sum(len(v) for v in deps.values())
    App.Console.PrintWarning(tr("“{file}” was closed: {n} linked part(s) are no longer "
                                "shown in the assembly.").format(file=label, n=count) + "\n")

    box = QtWidgets.QMessageBox(Gui.getMainWindow())
    box.setIcon(QtWidgets.QMessageBox.Warning)
    box.setWindowTitle(tr("Source file closed"))
    box.setText(tr("“{file}” was closed, but {n} part(s) of an open assembly are "
                   "linked to it: they are no longer shown.").format(file=label, n=count))
    box.setInformativeText(
        "\n".join(lines) + "\n\n" +
        tr("Freeze them: the file is reopened in the background, the parts are "
           "frozen into the assembly (dead copies), then the file is closed again. "
           "The assembly then no longer needs this file."))
    freeze_btn = box.addButton(tr("Freeze them"), QtWidgets.QMessageBox.AcceptRole)
    reopen_btn = box.addButton(tr("Reopen the file"), QtWidgets.QMessageBox.ActionRole)
    box.addButton(tr("Ignore"), QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(freeze_btn)
    run = getattr(box, "exec", None) or box.exec_
    run()
    clicked = box.clickedButton()
    if clicked not in (freeze_btn, reopen_btn):
        return

    keep = App.ActiveDocument
    src = docs.open_source(path, keep=App.getDocument(next(iter(deps))))
    for name in deps:
        try:
            App.getDocument(name).recompute()
        except Exception:
            pass
    if clicked is reopen_btn:
        App.Console.PrintMessage(tr("“{file}” reopened in the background.").format(
            file=label) + "\n")
        return

    from . import freeze
    for name, link_names in deps.items():
        d = App.getDocument(name)
        links = [d.getObject(n) for n in link_names if d.getObject(n) is not None]
        links = [l for l in links if l.LinkedObject is not None
                 and l.LinkedObject.Document is src]
        if links:
            freeze.figer(d, links)
    # Nothing links to the file any more: close it again (no new warning)
    if not _dependents(src):
        App.closeDocument(src.Name)
    if keep is not None and keep.Name in App.listDocuments():
        docs.activate(keep)


class _CloseGuard(object):
    """Document observer (App.addDocumentObserver). Keeps, for every Link
    pointing into another document, the name of that document (last known
    target); the detaching signals of FreeCAD alone are not reliable enough
    (they are not emitted for every Link when a document closes)."""

    def __init__(self):
        # (Link document name, Link name) -> target document name
        self._targets = {}

    def _record(self, obj):
        try:
            target = obj.LinkedObject
            if target is None:
                return              # detached: keep the last known target
            key = (obj.Document.Name, obj.Name)
            if target.Document is obj.Document:
                self._targets.pop(key, None)
            else:
                self._targets[key] = target.Document.Name
        except Exception:
            pass

    def _scan(self, doc):
        try:
            for o in doc.Objects:
                if o.isDerivedFrom("App::Link"):
                    self._record(o)
        except Exception:
            pass

    # Every property change goes through these two: return at once
    def slotBeforeChangeObject(self, obj, prop):
        if prop == "LinkedObject" and obj.isDerivedFrom("App::Link"):
            self._record(obj)

    def slotChangedObject(self, obj, prop):
        if prop == "LinkedObject" and obj.isDerivedFrom("App::Link"):
            self._record(obj)

    def slotRecomputedDocument(self, doc):
        self._scan(doc)

    def slotActivateDocument(self, doc):
        self._scan(doc)

    # --- unused frozen copies: refresh their mark after a part is deleted or
    # an undo / redo (deferred, documents must not change inside a signal)
    def slotDeletedObject(self, obj):
        try:
            if obj.isDerivedFrom("App::Link"):
                _schedule_unused(obj.Document.Name)
        except Exception:
            pass

    def slotUndoDocument(self, doc):
        _schedule_unused(doc.Name)

    def slotRedoDocument(self, doc):
        _schedule_unused(doc.Name)

    def slotDeletedDocument(self, doc):
        try:
            name = doc.Name
            deps = {}
            for (link_doc, link), target in list(self._targets.items()):
                if link_doc == name:
                    del self._targets[(link_doc, link)]
                elif target == name:
                    deps.setdefault(link_doc, []).append(link)
            if not deps or not prefs.get("WarnOnSourceClose"):
                return
            path, label = doc.FileName, doc.Label
            _QtWidgets, QtCore = _qt()
            # Never change documents inside the closing signal
            QtCore.QTimer.singleShot(0, lambda: _guarded(path, label, deps))
        except Exception as exc:
            App.Console.PrintWarning("Assembly Companion: close guard failed (%s)\n" % exc)


_unused_pending = set()


def _schedule_unused(doc_name):
    try:
        from .freeze import GROUPE_COPIES
        doc = App.getDocument(doc_name)
        if doc.getObject(GROUPE_COPIES) is None or doc_name in _unused_pending:
            return
        _unused_pending.add(doc_name)
        _QtWidgets, QtCore = _qt()
        QtCore.QTimer.singleShot(0, lambda: _mark_unused(doc_name))
    except Exception:
        pass


def _mark_unused(doc_name):
    _unused_pending.discard(doc_name)
    try:
        if doc_name in App.listDocuments():
            from .freeze import marquer_inutilisees
            marquer_inutilisees(App.getDocument(doc_name))
    except Exception as exc:
        App.Console.PrintWarning("Assembly Companion: unused copies not marked (%s)\n" % exc)


def _guarded(path, label, deps):
    try:
        _after_close(path, label, deps)
    except Exception as exc:
        import traceback
        App.Console.PrintError("Assembly Companion: %s\n%s\n" % (exc, traceback.format_exc()))


def install():
    global _observer
    if _observer is None:
        _observer = _CloseGuard()
        App.addDocumentObserver(_observer)
