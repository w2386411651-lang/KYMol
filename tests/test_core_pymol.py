"""Isolated real-engine checks. Synthetic models only; no GUI or user session."""

import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    import pymol2
except ImportError:
    pymol2 = None

from KYMol.core import KYMolController, KYMolError


@unittest.skipIf(pymol2 is None, "Requires a local PyMOL runtime")
class RealPyMOLControllerTests(unittest.TestCase):
    def setUp(self):
        self.pymol = pymol2.PyMOL()
        self.pymol.start()
        self.cmd = self.pymol.cmd
        self.cmd.fab("ACDEFGHIKLMNPQRSTVWY", "ref", chain="A")
        self.messages = []
        self.controller = KYMolController(self.cmd, self.messages.append)
        self.controller.set_selection(["ref"], active="ref")

    def tearDown(self):
        self.pymol.stop()

    def test_export_without_sele_writes_only_the_active_model(self):
        self.cmd.create("ref_extra", "ref")
        expected = self.cmd.count_atoms("ref")
        with tempfile.TemporaryDirectory(prefix="kymol-export-") as directory:
            for extension in ("pdb", "cif"):
                path = Path(directory, "export." + extension)
                self.controller.export_active(str(path), extension)
                self.cmd.load(str(path), "roundtrip")
                self.assertEqual(expected, self.cmd.count_atoms("roundtrip"))
                self.cmd.delete("roundtrip")

    def test_export_uses_only_selected_atoms_in_active_model(self):
        self.cmd.create("other", "ref")
        self.cmd.select("sele", "resi 1+2 and (ref or other)")
        selection = self.controller.active_selection()
        self.assertEqual(["ref"], self.cmd.get_object_list(selection))
        self.assertEqual(self.cmd.count_atoms("ref and resi 1+2"),
                         self.cmd.count_atoms(selection))

    def test_export_rejects_chain_expression_instead_of_expanding_selection(self):
        with self.assertRaises(KYMolError):
            self.controller.active_selection(chain="A or all")

    def test_export_cannot_overwrite_a_recorded_source(self):
        with tempfile.TemporaryDirectory(prefix="kymol-source-") as directory:
            path = Path(directory, "original.pdb")
            self.cmd.save(str(path), "ref")
            before = path.read_bytes()
            self.controller.sources.associate_source("ref", str(path))
            with self.assertRaisesRegex(KYMolError, "original source"):
                self.controller.export_active(str(path), "pdb")
            self.assertEqual(before, path.read_bytes())

    def test_missing_selection_is_clear_error_before_alignment(self):
        self.cmd.create("mobile", "ref")
        self.controller.set_selection(["ref", "mobile"], active="ref")
        with self.assertRaisesRegex(KYMolError, "Current selection"):
            self.controller.align_selected(scope="selection")

    def test_missing_target_chain_never_moves_mobile(self):
        self.cmd.create("mobile", "ref")
        self.cmd.translate([8, 2, 1], "mobile")
        before = self.cmd.get_coords("mobile").copy()
        self.controller.set_selection(["ref", "mobile"], active="ref")
        with self.assertRaises(KYMolError):
            self.controller.align_selected(chain="Z")
        np.testing.assert_array_equal(before, self.cmd.get_coords("mobile"))

    def test_later_invalid_mobile_never_partly_aligns_first_mobile(self):
        self.cmd.create("mobile_one", "ref")
        self.cmd.create("mobile_two", "ref")
        self.cmd.translate([8, 2, 1], "mobile_one")
        self.cmd.alter("mobile_two", "chain='Z'")
        before = self.cmd.get_coords("mobile_one").copy()
        self.controller.set_selection(["ref", "mobile_one", "mobile_two"], active="ref")
        with self.assertRaises(KYMolError):
            self.controller.align_selected(scope="common_chain")
        np.testing.assert_array_equal(before, self.cmd.get_coords("mobile_one"))

    def test_independent_alignment_keeps_target_fixed_and_native_undo_restores_batch(self):
        self.cmd.create("mobile_one", "ref")
        self.cmd.create("mobile_two", "ref")
        self.cmd.translate([8, 2, 1], "mobile_one")
        self.cmd.rotate("z", 43, "mobile_two")
        self.cmd.translate([-3, 4, 1], "mobile_two")
        before = {name: self.cmd.get_coords(name).copy()
                  for name in ("ref", "mobile_one", "mobile_two")}
        self.cmd.undo_enable()
        self.cmd.undo_clear_cache()
        self.controller.set_selection(["ref", "mobile_one", "mobile_two"], active="ref")
        self.controller.align_selected()
        np.testing.assert_array_equal(before["ref"], self.cmd.get_coords("ref"))
        for name in ("mobile_one", "mobile_two"):
            self.assertLess(self.cmd.rms_cur(name, "ref"), 1e-4)
        self.controller.undo()
        for name in before:
            np.testing.assert_allclose(before[name], self.cmd.get_coords(name), atol=1e-5)

    def test_blank_chain_copy_cut_preserve_atom_counts_and_undo(self):
        self.cmd.alter("ref", "chain=''")
        expected = self.cmd.count_atoms("ref")
        self.cmd.undo_enable()
        self.cmd.undo_clear_cache()
        copy_name = self.controller.copy_chains({"ref": [""]})[0]
        self.assertEqual(expected, self.cmd.count_atoms(copy_name))
        self.assertEqual(expected, self.cmd.count_atoms("ref"))
        self.controller.undo()
        self.assertNotIn(copy_name, self.cmd.get_names("objects"))
        cut_name = self.controller.cut_chains({"ref": [""]})[0]
        self.assertEqual(expected, self.cmd.count_atoms(cut_name))
        self.assertEqual(0, self.cmd.count_atoms("ref"))
        self.controller.undo()
        self.assertEqual(expected, self.cmd.count_atoms("ref"))
        self.assertNotIn(cut_name, self.cmd.get_names("objects"))

    def test_other_alignment_methods_keep_target_fixed(self):
        self.cmd.create("mobile", "ref")
        reference = self.cmd.get_coords("ref").copy()
        self.controller.set_selection(["ref", "mobile"], active="ref")
        for method in ("super", "cealign"):
            with self.subTest(method=method):
                self.cmd.translate([8, 2, 1], "mobile")
                self.controller.align_selected(method=method)
                np.testing.assert_array_equal(reference, self.cmd.get_coords("ref"))
                self.assertLess(self.cmd.rms_cur("mobile", "ref"), 1e-3)

    def test_copy_cut_preserve_all_states_and_source_metadata(self):
        self.cmd.create("ref", "ref", source_state=1, target_state=2)
        self.cmd.translate([1, 0, 0], "ref", state=2)
        before = [self.cmd.get_coords("ref", state=state).copy() for state in (1, 2)]
        with tempfile.TemporaryDirectory(prefix="kymol-states-") as directory:
            path = Path(directory, "original.pdb")
            self.cmd.save(str(path), "ref", state=0)
            self.controller.sources.associate_source("ref", str(path))
            self.cmd.group("test_group", "ref")
            self.controller.rename_active("renamed_ref")
            copied = self.controller.copy_chains({"renamed_ref": ["A"]})[0]
            cut = self.controller.cut_chains({"renamed_ref": ["A"]})[0]
            for name in (copied, cut):
                self.assertEqual(2, self.cmd.count_states(name))
                for state in (1, 2):
                    np.testing.assert_allclose(before[state - 1], self.cmd.get_coords(name, state=state))
                self.assertEqual(str(path.resolve()), self.controller.sources.record_for(name).paths[0])

    def test_copy_chains_treats_pattern_characters_as_literal_chain_ids(self):
        for index, chain in enumerate(("A", "B", "A*", "A+B", "A,B", 'A"B', "A'B")):
            self.cmd.pseudoatom("chain_fixture", pos=[index, 0, 0], chain=chain)
        for chain in ("A*", "A+B", "A,B", "A'B"):
            with self.subTest(chain=chain):
                name = self.controller.copy_chains({"chain_fixture": [chain]})[0]
                self.assertEqual(1, self.cmd.count_atoms(name))
                self.assertEqual([chain], self.cmd.get_chains(name))
        with self.assertRaisesRegex(KYMolError, "cannot be safely selected"):
            self.controller.copy_chains({"chain_fixture": ['A"B']})


if __name__ == "__main__":
    unittest.main()
