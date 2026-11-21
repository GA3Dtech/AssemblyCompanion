# SPDX-License-Identifier: LGPL-2.1-or-later
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

PARAMS = "User parameter:BaseApp/Preferences/Mod/AssemblyCompanion"

commands.register()

try:
    from . import prefs
    prefs.register()
except Exception as exc:
    App.Console.PrintWarning("Assembly Companion: preference page not added (%s)\n" % exc)


class AssemblyCompanionWorkbench(Gui.Workbench):
    """Workbench with two toolbars: durable assemblies and parts library."""

    MenuText = "Assembly Companion"
    ToolTip = ("Workshop-grade tools for FreeCAD's built-in Assembly: durable "
               "assemblies, visual parts library, selection sets.")
    Icon = icon("AssemblyCompanion.svg")

    def Initialize(self):
        self.appendToolbar("Companion - Durable", commands.TOOLBAR_DURABLE)
        self.appendToolbar("Companion - Library", commands.TOOLBAR_LIBRARY)
        self.appendMenu("Assembly Companion", commands.MENU)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(AssemblyCompanionWorkbench())


# --------------------------------------------------------------------------
#  Tools inside the built-in Assembly workbench (WorkbenchManipulator,
#  FreeCAD 0.22 / 1.0+). Can be turned off with the boolean parameter
#  ShowInAssemblyWorkbench.
# --------------------------------------------------------------------------

class _AssemblyWorkbenchManipulator:
    """Extends the "Assembly" toolbar of the Assembly workbench with the
    Companion commands when that workbench is active; leaves every other
    workbench untouched.

    "append" only adds to a toolbar that ALREADY exists in the workbench
    (FreeCAD silently ignores an unknown toolbar name), so the commands go to
    the built-in "Assembly" toolbar (untranslated name), after a separator."""

    TOOLBAR = "Assembly"

    def modifyToolBars(self):
        try:
            if Gui.activeWorkbench().name() != "AssemblyWorkbench":
                return []
        except Exception:
            return []
        cmds = (["Separator"] + commands.TOOLBAR_DURABLE
                + ["Separator"] + commands.TOOLBAR_LIBRARY)
        return [{"append": c, "toolBar": self.TOOLBAR} for c in cmds]


try:
    if App.ParamGet(PARAMS).GetBool("ShowInAssemblyWorkbench", True) and \
            hasattr(Gui, "addWorkbenchManipulator"):
        Gui.addWorkbenchManipulator(_AssemblyWorkbenchManipulator())
except Exception as exc:
    App.Console.PrintWarning("Assembly Companion: Assembly toolbar not added (%s)\n" % exc)

App.Console.PrintLog("Assembly Companion %s loaded\n" % __version__)
