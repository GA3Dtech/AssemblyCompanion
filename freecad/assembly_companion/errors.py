# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
"""
errors.py (Assembly Companion) - exceptions of the public API (api.py).

Callers test the TYPE; the message is translated (i18n.tr) for people.
Every exception also carries `details`, a dict of plain values that can be
serialised to JSON (object names, file paths...).
"""


class AssemblyCompanionError(Exception):
    """Base class of every error raised by the API."""

    def __init__(self, message="", **details):
        super(AssemblyCompanionError, self).__init__(message)
        self.details = details

    def to_dict(self):
        return {"error": type(self).__name__, "message": str(self), "details": self.details}


class NoDocumentError(AssemblyCompanionError):
    """No document given, or no open document with that name."""


class NoAssemblyError(AssemblyCompanionError):
    """The document holds no assembly (or not the one asked for)."""


class ObjectNotFoundError(AssemblyCompanionError):
    """An object name does not exist in the document."""


class UnsupportedObjectError(AssemblyCompanionError):
    """The object exists but the operation does not apply to it."""


class SourceNotFoundError(AssemblyCompanionError):
    """A source file (or an object in it) cannot be found."""


class GuiRequiredError(AssemblyCompanionError):
    """The operation needs the FreeCAD GUI (e.g. reactivating an assembly)."""
