# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - API exceptions
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
