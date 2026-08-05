"""KyMol: an active-object workflow for PyMOL 2.x.

Install this directory as a zipped PyMOL plugin.  The module deliberately
creates only normal PyMOL selections/objects and uses cmd.save(), so a PSE
created after using it opens normally without KyMol installed.
"""

from .core import KYMolController

__version__ = "0.6.1"

_controller = None
_dialog = None


def controller():
    """Return the singleton controller, creating it only inside PyMOL."""
    global _controller
    if _controller is None:
        from pymol import cmd
        _controller = KYMolController(cmd)
    return _controller


def ky_sync_selection():
    """Import the objects represented by PyMOL's current ``sele``."""
    return controller().sync_from_pymol_selection()


def ky_align_selected(method="align", scope="auto", chain=""):
    """Align selected KyMol objects to the active KyMol object."""
    return controller().align_selected(method=method, scope=scope, chain=chain)


def ky_color_selected():
    """Color chains in the selected KyMol objects."""
    return controller().color_selected_by_chain()


def open_panel():
    """Open (or raise) the KyMol PyQt panel."""
    global _dialog
    if _dialog is None:
        from .ui import KYMolDialog
        _dialog = KYMolDialog(controller())
    _dialog.refresh_objects(keep_selection=True)
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()


def _show_panel_from_shortcut():
    try:
        open_panel()
    except Exception as exc:  # PyMOL must remain usable if Qt is unavailable
        print("[KyMol] Could not open panel: {}".format(exc))


def __init_plugin__(app=None):
    """PyMOL plugin entry point."""
    from pymol import cmd
    from pymol.plugins import addmenuitemqt

    addmenuitemqt("KyMol: Structure Review Panel", open_panel)
    cmd.extend("ky_sync_selection", ky_sync_selection)
    cmd.extend("ky_align_selected", ky_align_selected)
    cmd.extend("ky_color_selected", ky_color_selected)

    # PyMOL documents ALT-letter shortcuts but not multiple modifiers.
    # ALT-A is the guaranteed global fallback for the panel's Shift+Alt+A.
    cmd.set_key("ALT-A", ky_align_selected)
    cmd.set_key("ALT-C", ky_color_selected)
    print("[KyMol] v{} loaded. Open Plugin > KyMol: Structure Review Panel.".format(__version__))
