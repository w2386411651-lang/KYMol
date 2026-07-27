"""KYPyMol: an active-object workflow for PyMOL 2.x.

Install this directory as a zipped PyMOL plugin.  The module deliberately
creates only normal PyMOL selections/objects and uses cmd.save(), so a PSE
created after using it opens normally without KYPyMol installed.
"""

from .core import KYPyMolController

__version__ = "0.1.0"

_controller = None
_dialog = None


def controller():
    """Return the singleton controller, creating it only inside PyMOL."""
    global _controller
    if _controller is None:
        from pymol import cmd
        _controller = KYPyMolController(cmd)
    return _controller


def ky_sync_selection():
    """Import the objects represented by PyMOL's current ``sele``."""
    return controller().sync_from_pymol_selection()


def ky_align_selected(method="super", scope="auto", chain=""):
    """Align selected KYPyMol objects to the active KYPyMol object."""
    return controller().align_selected(method=method, scope=scope, chain=chain)


def ky_color_selected():
    """Color chains in the selected KYPyMol objects."""
    return controller().color_selected_by_chain()


def open_panel():
    """Open (or raise) the KYPyMol PyQt panel."""
    global _dialog
    if _dialog is None:
        from .ui import KYPyMolDialog
        _dialog = KYPyMolDialog(controller())
    _dialog.refresh_objects(keep_selection=True)
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()


def _show_panel_from_shortcut():
    try:
        open_panel()
    except Exception as exc:  # PyMOL must remain usable if Qt is unavailable
        print("[KYPyMol] Could not open panel: {}".format(exc))


def __init_plugin__(app=None):
    """PyMOL plugin entry point."""
    from pymol import cmd
    from pymol.plugins import addmenuitemqt

    addmenuitemqt("KYPyMol: Active Object Panel", open_panel)
    cmd.extend("ky_sync_selection", ky_sync_selection)
    cmd.extend("ky_align_selected", ky_align_selected)
    cmd.extend("ky_color_selected", ky_color_selected)

    # PyMOL documents ALT-letter shortcuts but not multiple modifiers.
    # ALT-A is the guaranteed global fallback for the panel's Shift+Alt+A.
    cmd.set_key("ALT-A", ky_align_selected)
    cmd.set_key("ALT-C", ky_color_selected)
    print("[KYPyMol] v{} loaded. Plugin menu opens the panel; ALT-A aligns, ALT-C colors chains.".format(__version__))
