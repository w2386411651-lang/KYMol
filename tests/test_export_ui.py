"""Source-directory and source-file protection through the actual export UI."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pymol.Qt import QtWidgets
import pymol2
from KYMol.core import KYMolController
from KYMol.ui import KYMolDialog


class ExportDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kymol-export-ui-")
        self.addCleanup(self.temp.cleanup)
        self.engine = pymol2.PyMOL()
        self.engine.start()
        self.addCleanup(self.engine.stop)
        self.cmd = self.engine.cmd
        self.controller = KYMolController(self.cmd, reporter=lambda _: None)
        self.sources = {}
        for name in ("model_first", "model_second"):
            folder = Path(self.temp.name) / name
            folder.mkdir()
            path = folder / (name + ".pdb")
            self.cmd.pseudoatom(name, name="CA", resn="ALA", chain="A", elem="C")
            self.cmd.save(str(path), name)
            self.controller.sources.associate_source(name, str(path))
            self.sources[name] = path
        self.controller.set_selection(["model_first", "model_second"], active="model_second")
        self.dialog = KYMolDialog(self.controller)
        self.addCleanup(self.dialog.close)
        self.dialog.chain_visual_timer.stop()
        self.controller.set_selection(["model_first", "model_second"], active="model_second")
        self.dialog.refresh_objects(keep_selection=True)

    def test_export_dialog_uses_active_source_for_both_formats_under_multiselection(self):
        for fmt in ("pdb", "cif"):
            with self.subTest(fmt=fmt), patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")) as picker:
                self.dialog.export(fmt)
            initial = Path(picker.call_args.args[2])
            self.assertEqual(self.sources["model_second"].parent, initial.parent)
            self.assertIn("model_second", initial.name)
            self.assertNotEqual(self.sources["model_second"], initial)
        self.assertEqual(["model_first", "model_second"], self.controller.state.selected)
        self.assertEqual("model_second", self.controller.state.active)

    def test_export_without_active_object_does_not_open_save_dialog(self):
        self.controller.set_selection([])
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")) as picker:
            self.dialog.export("pdb")
        picker.assert_not_called()
        self.assertIn("active", self.dialog.status.toPlainText().lower())

    def test_export_never_overwrites_a_recorded_source_of_any_model(self):
        path = self.sources["model_first"]
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.dialog.export("pdb")
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIn("source", self.dialog.status.toPlainText().lower())

    def test_missing_extension_existing_export_needs_confirmation(self):
        path = Path(self.temp.name) / "existing_export.pdb"
        path.write_text("keep prior export", encoding="ascii")
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path.with_suffix("")), "")), \
             patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No) as confirm:
            self.dialog.export("pdb")
        confirm.assert_called_once()
        self.assertEqual("keep prior export", path.read_text(encoding="ascii"))

    def test_unknown_source_uses_previous_export_directory_and_explains_fallback(self):
        self.cmd.pseudoatom("unknown", name="CA", resn="ALA")
        self.controller.set_selection(["unknown"], active="unknown")
        self.dialog._last_export_directory = self.temp.name
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")) as picker:
            self.dialog.export("cif")
        self.assertEqual(Path(self.temp.name), Path(picker.call_args.args[2]).parent)
        self.assertIn("unknown", self.dialog.status.toPlainText().lower())

    def test_user_can_associate_an_original_file_for_a_preexisting_object(self):
        self.cmd.pseudoatom("preexisting", name="CA", resn="ALA")
        self.controller.set_selection(["preexisting"], active="preexisting")
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value=(str(self.sources["model_first"]), "")):
            self.dialog.associate_source()
        record = self.controller.sources.record_for("preexisting")
        self.assertEqual((str(self.sources["model_first"]),), record.paths)
        self.assertEqual("user_associated", record.evidence)

    def test_active_target_switch_inside_save_picker_cancels_export(self):
        path = Path(self.temp.name) / "second_export.pdb"
        def picker(*args, **kwargs):
            self.controller.set_active("model_first")
            return str(path), ""
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", side_effect=picker):
            self.dialog.export("pdb")
        self.assertFalse(path.exists(), "Must not save a different active target under the original model's path")
        self.assertIn("changed", self.dialog.status.toPlainText().lower())

    def test_active_target_switch_inside_overwrite_confirmation_keeps_existing_file(self):
        path = Path(self.temp.name) / "existing.pdb"
        path.write_text("prior export", encoding="ascii")
        def confirm(*args, **kwargs):
            self.controller.set_active("model_first")
            return QtWidgets.QMessageBox.Yes
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")), \
             patch.object(QtWidgets.QMessageBox, "question", side_effect=confirm):
            self.dialog.export("pdb")
        self.assertEqual("prior export", path.read_text(encoding="ascii"))
        self.assertIn("changed", self.dialog.status.toPlainText().lower())

    def test_same_size_atom_selection_change_inside_picker_cancels_export(self):
        self.cmd.pseudoatom("model_second", name="CB", resn="ALA", chain="A", elem="C", resi="2")
        self.cmd.select("sele", "model_second and name CA")
        self.dialog.export_mode.setCurrentIndex(self.dialog.export_mode.findData(False))
        path = Path(self.temp.name) / "selected_ca.pdb"
        def picker(*args, **kwargs):
            self.cmd.select("sele", "model_second and name CB")
            return str(path), ""
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", side_effect=picker):
            self.dialog.export("pdb")
        self.assertFalse(path.exists(), "Equal atom counts must not hide a changed atom selection")
        self.assertIn("changed", self.dialog.status.toPlainText().lower())

    def test_unchanged_atom_selection_still_exports_successfully(self):
        self.cmd.pseudoatom("model_second", name="CB", resn="ALA", chain="A", elem="C", resi="2")
        self.cmd.select("sele", "model_second and name CA")
        self.dialog.export_mode.setCurrentIndex(self.dialog.export_mode.findData(False))
        path = Path(self.temp.name) / "selected_ca.pdb"
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.dialog.export("pdb")
        self.assertTrue(path.exists())
        self.cmd.load(str(path), "roundtrip")
        self.assertEqual(1, self.cmd.count_atoms("roundtrip"))
        self.assertEqual(1, self.cmd.count_atoms("roundtrip and name CA"))


if __name__ == "__main__":
    unittest.main()
