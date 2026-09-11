"""KyMol: an active-object workflow for PyMOL 2.x.

Install this directory as a zipped PyMOL plugin.  The module deliberately
creates only normal PyMOL selections/objects and uses cmd.save(), so a PSE
created after using it opens normally without KyMol installed.
"""

import importlib
import sys
import gc


def _prepare_package_reload():
    """Retire only this package's Python/UI state, leaving PyMOL objects intact.

    PyMOL's installer reloads the package but leaves its submodules cached. A
    failed rc1 upgrade also loses the package's old dialog reference, so recover
    that reference from Qt before replacing any of the private modules.
    """
    old_core = sys.modules.get(__name__ + ".core")
    if old_core is None:
        return None
    previous = globals().get("_controller")
    snapshot = {}
    old_ui = sys.modules.get(__name__ + ".ui")
    if old_ui is not None:
        widgets = old_ui.QtWidgets
        app = widgets.QApplication.instance()
        dialogs = [] if app is None else [
            widget for widget in app.topLevelWidgets()
            if type(widget).__module__ == __name__ + ".ui"
            and type(widget).__name__ == "KYMolDialog"
        ]
        dialogs.sort(key=lambda widget: (widget.isActiveWindow(), widget.isVisible()),
                     reverse=True)
        if dialogs:
            previous = dialogs[0].controller
            snapshot["geometry"] = dialogs[0].saveGeometry()
        for dialog in dialogs:
            for timer in dialog.findChildren(old_ui.QtCore.QTimer):
                timer.stop()
            for shortcut in dialog.findChildren(widgets.QShortcut):
                shortcut.setEnabled(False)
            hotbox = getattr(dialog, "mode_hotbox", None)
            if hotbox is not None:
                hotbox.close()
            dialog.close()
            dialog.deleteLater()
    if previous is not None:
        snapshot["selected"] = list(previous.state.selected)
        snapshot["active"] = previous.state.active
        for key in ("_group_name_history", "_undo_history", "_redo_history", "_history_serial"):
            snapshot[key] = getattr(previous, key)
    # Source records live on molecular objects; replacing the observer neither
    # changes those records nor reloads any structure. Consult cmd's own dict:
    # pymol2 proxies otherwise forward missing attributes to the global engine.
    command = previous.cmd if previous is not None else sys.modules.get("pymol.cmd")
    if command is not None:
        tracker = vars(command).get("_kymol_source_tracker")
        if tracker is not None and type(tracker).__module__ == __name__ + ".provenance":
            tracker.uninstall()
            if vars(command).get("_kymol_source_tracker") is tracker:
                delattr(command, "_kymol_source_tracker")
    importlib.invalidate_caches()
    # Fresh modules keep retired callbacks bound to their own old globals,
    # instead of mixing new exception/data classes into still-live old code.
    for suffix in ("ui", "core", "provenance"):
        sys.modules.pop(__name__ + "." + suffix, None)
        globals().pop(suffix, None)
    return snapshot


_reload_state = _prepare_package_reload()
KYMolController = importlib.import_module(__name__ + ".core").KYMolController

__version__ = "0.7.0rc2"

_controller = None
_dialog = None
_menu_registered = globals().get("_menu_registered", False)


def controller():
    """Return the singleton controller, creating it only inside PyMOL."""
    global _controller
    if _controller is None:
        from pymol import cmd
        _controller = KYMolController(cmd)
        if _reload_state:
            _controller.set_selection(_reload_state.get("selected", []),
                                      _reload_state.get("active"))
            for key in ("_group_name_history", "_undo_history", "_redo_history", "_history_serial"):
                if key in _reload_state:
                    setattr(_controller, key, _reload_state[key])
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
        if _reload_state and "geometry" in _reload_state:
            _dialog.restoreGeometry(_reload_state["geometry"])
    _dialog.refresh_objects(keep_selection=True)
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()


def _show_panel_from_shortcut():
    try:
        open_panel()
    except Exception as exc:  # PyMOL must remain usable if Qt is unavailable
        print("[KyMol] Could not open panel: {}".format(exc))


def _register_panel_menu():
    """Reuse KyMol's existing Qt action across installs, including pre-rc2 ones."""
    global _menu_registered
    from pymol.plugins import addmenuitemqt, get_pmgapp
    label = "KyMol: Structure Review Panel"
    app = get_pmgapp()
    menus = getattr(getattr(app, "menuBar", None), "_menudict", {})
    menu = menus.get("PluginQt")
    if menu is not None:
        if any(action.property("kymolPackage") == __name__ for action in menu.actions()):
            _menu_registered = True
            return
        # PyMOL's Qt menu retains a Python exception wrapper with the command
        # in its defaults. Legacy callbacks still reference this same package
        # globals dict after reload. Reuse them by provenance, never by label:
        # another installed alias can legitimately have the same visible text.
        for wrapper in gc.get_referents(menu):
            for command in getattr(wrapper, "__defaults__", ()) or ():
                if (getattr(command, "__globals__", None) is globals()
                        and getattr(command, "__name__", None) == "open_panel"):
                    _menu_registered = True
                    return
    if not _menu_registered or menu is not None:
        before = [] if menu is None else list(menu.actions())
        addmenuitemqt(label, open_panel)
        _menu_registered = True
        if menu is not None:
            for action in menu.actions():
                if action not in before:
                    action.setProperty("kymolPackage", __name__)


def __init_plugin__(app=None):
    """PyMOL plugin entry point."""
    from pymol import cmd

    # Install before opening the panel so ordinary File > Open and load commands
    # retain reliable source folders. Existing unidentified objects stay unknown.
    controller().sources.install()
    _register_panel_menu()
    cmd.extend("ky_sync_selection", ky_sync_selection)
    cmd.extend("ky_align_selected", ky_align_selected)
    cmd.extend("ky_color_selected", ky_color_selected)

    # PyMOL documents ALT-letter shortcuts but not multiple modifiers.
    # ALT-A is the guaranteed global fallback for the panel's Shift+Alt+A.
    cmd.set_key("ALT-A", ky_align_selected)
    cmd.set_key("ALT-C", ky_color_selected)
    print("[KyMol] v{} loaded. Open Plugin > KyMol: Structure Review Panel.".format(__version__))
