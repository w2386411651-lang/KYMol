"""In-process upgrade regressions using unique temporary plugin packages.

No installed plugin, PyMOL preferences or real user session is touched.  The
legacy fixture deliberately has no source-tracking API: a parent-only rc1
reload reproduces the reported failure before the current entry point recovers.
"""

import importlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import pymol
    import pymol2
    import pymol.plugins
    from pymol.Qt import QtCore, QtWidgets
    from pmg_qt.mimic_pmg_tk import PmwMenuBar
except ImportError:
    pymol2 = None


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "KYMol"
LEGACY_CORE = '''
from types import SimpleNamespace
class KYMolError(RuntimeError):
    pass
class KYMolController:
    def __init__(self, cmd):
        self.cmd = cmd
        self.state = SimpleNamespace(selected=[], active=None)
        self._group_name_history = set()
        self._undo_history = []
        self._redo_history = []
        self._history_serial = 0
    def set_selection(self, names, active=None):
        self.state.selected = list(names)
        self.state.active = active
'''
LEGACY_UI = '''
from pymol.Qt import QtCore, QtWidgets
from .core import KYMolError
class KYMolDialog(QtWidgets.QDialog):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.chain_visual_timer = QtCore.QTimer(self)
        self.chain_visual_timer.setInterval(60000)
        self.chain_visual_timer.start()
'''
# This is the relevant original parent-only initialization contract, including
# the rc1 access that fails with a cached pre-source-tracking controller class.
PARENT_ONLY_ENTRY = '''
from .core import KYMolController
_controller = None
_dialog = None
def controller():
    global _controller
    if _controller is None:
        from pymol import cmd
        _controller = KYMolController(cmd)
    return _controller
def open_panel():
    global _dialog
    if _dialog is None:
        from .ui import KYMolDialog
        _dialog = KYMolDialog(controller())
    _dialog.show()
def __init_plugin__(app=None):
    from pymol.plugins import addmenuitemqt
    controller().sources.install()
    addmenuitemqt("KyMol: Structure Review Panel", open_panel)
'''
PDB = ("ATOM      1  CA  GLY A   1       0.000   0.000   0.000  1.00 20.00           C  \n"
       "ATOM      2  CA  ALA B   2       2.000   0.000   0.000  1.00 20.00           C  \nEND\n")


@unittest.skipIf(pymol2 is None, "Requires a local PyMOL and Qt runtime")
class PluginReloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kymol-upgrade-test-")
        self.root = Path(self.temp.name)
        self.package_name = "kymol_upgrade_" + uuid.uuid4().hex
        self.package_dir = self.root / self.package_name
        self.package_dir.mkdir()
        self.native = pymol2.PyMOL()
        self.native.start()
        self.cmd = self.native.cmd
        self.menu = QtWidgets.QMenu()
        self.pmgapp = types.SimpleNamespace(
            menuBar=PmwMenuBar({"PluginQt": self.menu}))
        self.patches = [patch.object(pymol, "cmd", self.cmd),
                        patch.object(pymol.plugins, "get_pmgapp", return_value=self.pmgapp),
                        patch.object(pymol.plugins, "HAVE_QT", True)]
        for item in self.patches:
            item.start()
        sys.path.insert(0, str(self.root))

    def tearDown(self):
        # Retire only widgets/modules/observers belonging to this temporary alias.
        for widget in self.qt.topLevelWidgets():
            if type(widget).__module__.startswith(self.package_name + "."):
                for timer in widget.findChildren(QtCore.QTimer):
                    timer.stop()
                widget.close()
                widget.deleteLater()
        tracker = vars(self.cmd).get("_kymol_source_tracker")
        if tracker is not None:
            tracker.uninstall()
            delattr(self.cmd, "_kymol_source_tracker")
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.menu.close()
        self.menu.deleteLater()
        for item in reversed(self.patches):
            item.stop()
        self.native.stop()
        for key in list(sys.modules):
            if key == self.package_name or key.startswith(self.package_name + "."):
                del sys.modules[key]
        sys.path.remove(str(self.root))
        self.temp.cleanup()

    def _copy_current(self):
        for name in ("__init__.py", "core.py", "ui.py", "provenance.py"):
            shutil.copyfile(SOURCE_ROOT / name, self.package_dir / name)
        importlib.invalidate_caches()

    def _import_package(self):
        return importlib.import_module(self.package_name)

    def test_parent_only_rc1_failure_then_current_recovers_live_legacy_dialog(self):
        (self.package_dir / "__init__.py").write_text(PARENT_ONLY_ENTRY, encoding="utf-8")
        (self.package_dir / "core.py").write_text(LEGACY_CORE, encoding="utf-8")
        (self.package_dir / "ui.py").write_text(LEGACY_UI, encoding="utf-8")
        package = self._import_package()
        self.cmd.read_pdbstr(PDB, "kept_obj")
        package.controller().set_selection(["kept_obj"], "kept_obj")
        package.open_panel()
        old_dialog = package._dialog
        old_timer = old_dialog.chain_visual_timer
        old_class = type(package._controller)
        old_error = sys.modules[self.package_name + ".ui"].KYMolError
        self.assertTrue(old_timer.isActive())
        # Register the actual PyMOL legacy menu wrapper before the upgrade.
        pymol.plugins.addmenuitemqt("KyMol: Structure Review Panel", package.open_panel)
        original_coords = self.cmd.get_coords("kept_obj").tolist()

        # On-disk submodules are now new, while Python still caches the old ones.
        self._copy_current()
        (self.package_dir / "__init__.py").write_text(PARENT_ONLY_ENTRY, encoding="utf-8")
        importlib.reload(package)
        with self.assertRaisesRegex(AttributeError, "sources"):
            package.__init_plugin__()
        self.assertIsNone(package._dialog)  # Failed rc1 loses its old dialog reference.
        self.assertIs(type(package._controller), old_class)
        self.assertTrue(old_timer.isActive())

        shutil.copyfile(SOURCE_ROOT / "__init__.py", self.package_dir / "__init__.py")
        importlib.invalidate_caches()
        importlib.reload(package)
        self.assertFalse(old_timer.isActive())
        self.assertFalse(old_dialog.isVisible())
        package.__init_plugin__()
        package.open_panel()
        current_core = importlib.import_module(self.package_name + ".core")
        current_ui = importlib.import_module(self.package_name + ".ui")
        self.assertIs(type(package.controller()), current_core.KYMolController)
        self.assertIsNot(type(package.controller()), old_class)
        self.assertTrue(hasattr(package.controller(), "sources"))
        self.assertIs(current_ui.KYMolError, current_core.KYMolError)
        self.assertIsNot(current_ui.KYMolError, old_error)
        self.assertEqual(package.controller().state.selected, ["kept_obj"])
        self.assertEqual(package.controller().state.active, "kept_obj")
        self.assertEqual(self.cmd.get_coords("kept_obj").tolist(), original_coords)
        self.assertEqual(len(self.menu.actions()), 1)

    def test_repeated_reload_replaces_tracker_without_stacking_or_losing_source(self):
        self._copy_current()
        package = self._import_package()
        unwrapped_load = self.cmd.load
        package.__init_plugin__()
        source = self.root / "synthetic_source.pdb"
        source.write_text(PDB, encoding="ascii")
        original_bytes = source.read_bytes()
        self.cmd.load(str(source), "kept_obj")
        package.controller().set_selection(["kept_obj"], "kept_obj")
        package.open_panel()

        for _ in range(2):
            old_tracker = package.controller().sources
            old_timer = package._dialog.chain_visual_timer
            importlib.reload(package)
            self.assertFalse(old_timer.isActive())
            package.__init_plugin__()
            package.open_panel()
            current_tracker = package.controller().sources
            self.assertIsNot(current_tracker, old_tracker)
            self.assertFalse(old_tracker._installed)
            self.assertEqual(old_tracker._patches, [])
            self.assertIs(self.cmd.load.__wrapped__, unwrapped_load)
            self.assertEqual(current_tracker.record_for("kept_obj").paths, (str(source),))
            self.assertEqual(package.controller().state.active, "kept_obj")
            self.assertEqual(len(self.menu.actions()), 1)
            with patch.object(old_tracker, "apply", wraps=old_tracker.apply) as retired_write:
                self.cmd.load(str(source), "after_reload")
                self.assertTrue(current_tracker.record_for("after_reload").complete)
                retired_write.assert_not_called()
            self.cmd.delete("after_reload")
        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertEqual(self.cmd.count_atoms("kept_obj"), 2)


if __name__ == "__main__":
    unittest.main()
