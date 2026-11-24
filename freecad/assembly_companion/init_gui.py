# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Assembly Companion - workbench registration
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
init_gui.py (Assembly Companion) - registers the workbench, its commands, and
(optionally) adds its tools to the toolbar area of FreeCAD's built-in Assembly
workbench, so they are at hand without switching workbench.

Namespace-package layout (FreeCAD workbench starter kit): FreeCAD imports
freecad.assembly_companion and runs this module at startup.
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import icon, __version__
from . import commands
from .i18n import tr

commands.register()

from . import prefs  # noqa: E402  (after the commands are registered)

try:
    # The preference dialog looks for an icon named "preferences-<group>"
    # (lower case, spaces as "_") in the icon search path
    from . import ICON_DIR
    Gui.addIconPath(ICON_DIR)
    prefs.register()
except Exception as exc:
    App.Console.PrintWarning("Assembly Companion: preference page not added (%s)\n" % exc)


class AssemblyCompanionWorkbench(Gui.Workbench):
    """Workbench with two toolbars: durable assemblies and parts library."""

    MenuText = "Assembly Companion"
    ToolTip = tr("Workshop-grade tools for FreeCAD's built-in Assembly: durable "
               "assemblies, visual parts library, selection sets.")
    Icon = icon("AssemblyCompanion.svg")

    def Initialize(self):
        self.appendToolbar("Assembly Companion", commands.TOOLBAR)
        self.appendMenu("Assembly Companion", commands.MENU)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(AssemblyCompanionWorkbench())


# --------------------------------------------------------------------------
#  Toolbar inside the built-in Assembly workbench. Can be turned off with
#  the preference ShowInAssemblyWorkbench.
# --------------------------------------------------------------------------

ASM_TOOLBARS = "User parameter:BaseApp/Workbench/AssemblyWorkbench/Toolbar"
ASM_TOOLBAR_GROUP = "AssemblyCompanion"
ASM_TOOLBAR_NAME = "Assembly Companion"


def sync_assembly_toolbar():
    """Declare the Companion commands as a custom toolbar of the Assembly
    workbench (the mechanism of Tools > Customize > Toolbars): FreeCAD builds
    it as a separate toolbar the user can move, dock anywhere or hide, and
    remembers its position. A WorkbenchManipulator could only append the
    commands to the existing "Assembly" toolbar, which cannot be split.

    Rewritten at every start so it follows the command list; the "Active"
    flag set by the user in the Customize dialog is kept."""
    grp = App.ParamGet(ASM_TOOLBARS)
    active = True
    if grp.HasGroup(ASM_TOOLBAR_GROUP):
        active = grp.GetGroup(ASM_TOOLBAR_GROUP).GetBool("Active", True)
        grp.RemGroup(ASM_TOOLBAR_GROUP)
    if not prefs.get("ShowInAssemblyWorkbench"):
        return
    bar = grp.GetGroup(ASM_TOOLBAR_GROUP)
    bar.SetString("Name", ASM_TOOLBAR_NAME)
    bar.SetBool("Active", active)
    cmds = commands.TOOLBAR
    for i, cmd in enumerate(cmds):
        if cmd == "Separator":
            bar.SetString("Separator%d" % i, "")
        else:
            # Module FreeCAD imports if the command is not registered yet
            bar.SetString(cmd, "freecad.assembly_companion.init_gui")


try:
    sync_assembly_toolbar()
except Exception as exc:
    App.Console.PrintWarning("Assembly Companion: Assembly toolbar not added (%s)\n" % exc)

try:
    from . import close_guard
    close_guard.install()
except Exception as exc:
    App.Console.PrintWarning("Assembly Companion: close guard not installed (%s)\n" % exc)

try:
    from . import lightweight
    lightweight.install()
except Exception as exc:
    App.Console.PrintWarning("Assembly Companion: lightweight level of detail not "
                             "installed (%s)\n" % exc)

App.Console.PrintLog("Assembly Companion %s loaded\n" % __version__)
