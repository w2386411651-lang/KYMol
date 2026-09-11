import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from KYMol.provenance import PROPERTY, SourceRecord, SourceTracker, get_tracker

try:
    import pymol2
except ImportError:
    pymol2 = None


PDB = ("ATOM      1  CA  GLY A   1       0.000   0.000   0.000  1.00 20.00           C  \n"
       "ATOM      2  CA  ALA B   2       2.000   0.000   0.000  1.00 20.00           C  \nEND\n")


class PropertyCmd:
    def __init__(self):
        self.properties = {"model": {}}

    def get_names_of_type(self, _type):
        return list(self.properties)

    def get_property(self, prop, name):
        return self.properties.get(name, {}).get(prop)

    def set_property(self, prop, value, name, **kwargs):
        self.properties[name][prop] = value


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "model.pdb"
        self.source.write_text(PDB)
        self.cmd = PropertyCmd()
        self.tracker = get_tracker(self.cmd)

    def test_association_and_collision_free_default_preserve_source(self):
        before = self.source.read_bytes()
        self.tracker.associate_source("model", self.source)
        result = self.tracker.export_default("model", "pdb")
        self.assertEqual(result.directory, str(self.root))
        self.assertFalse(result.used_fallback)
        self.assertEqual(Path(result.path).name, "model_export.pdb")
        Path(result.path).write_text("existing export")
        second = self.tracker.export_default("model", "pdb")
        self.assertEqual(Path(second.path).name, "model_export_2.pdb")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(self.tracker.is_source_path(str(self.source)))

    def test_unknown_source_never_guessed_from_model_name(self):
        suggestion = self.tracker.export_default("model", "cif", self.temp.name)
        self.assertTrue(suggestion.used_fallback)
        self.assertIn("unknown", suggestion.reason)
        self.assertFalse(self.tracker.record_for("model").complete)

    def test_nonwritable_source_has_clear_fallback(self):
        self.tracker.associate_source("model", self.source)
        fallback = self.root / "fallback"
        fallback.mkdir()
        with patch("KYMol.provenance.directory_writable", side_effect=lambda p: p == str(fallback)):
            suggestion = self.tracker.export_default("model", "pdb", str(fallback))
        self.assertEqual(suggestion.directory, str(fallback))
        self.assertTrue(suggestion.used_fallback)
        self.assertIn("not writable", suggestion.reason)

    def test_mixed_and_partial_sources_use_explicit_fallback(self):
        another = self.root / "another" / "two.cif"
        self.tracker.apply("model", SourceRecord((str(self.source), str(another)), True))
        self.assertIn("multiple source folders", self.tracker.export_default("model", "cif").reason)
        self.tracker.apply("model", SourceRecord((str(self.source),), False))
        self.assertIn("Some source data is unknown", self.tracker.export_default("model", "cif").reason)

    def test_corrupt_properties_are_unknown_and_invalid_associations_rejected(self):
        for raw in ("broken", "[]", '{"version":1,"paths":[3]}',
                    '{"version":1,"paths":["relative/file.pdb"]}'):
            self.cmd.properties["model"][PROPERTY] = raw
            self.assertFalse(self.tracker.record_for("model").complete)
        with self.assertRaises(ValueError):
            self.tracker.associate_source("missing", self.source)
        with self.assertRaises(ValueError):
            self.tracker.associate_source("model", self.root / "missing.pdb")

    def test_source_protection_covers_other_objects(self):
        self.tracker.associate_source("model", self.source)
        self.cmd.properties["other"] = {}
        self.assertTrue(self.tracker.is_source_path(str(self.source), "other"))

    def test_tracker_is_owned_by_cmd_not_inherited_from_global_proxy(self):
        original_tracker = self.tracker

        class ProxyCmd(PropertyCmd):
            def __getattr__(self, name):
                if name == "_kymol_source_tracker":
                    return original_tracker
                raise AttributeError(name)

        other = ProxyCmd()
        tracker = get_tracker(other)
        self.assertIsNot(tracker, original_tracker)
        self.assertIs(tracker.cmd, other)


@unittest.skipIf(pymol2 is None, "Real PyMOL is unavailable")
class RealPyMOLProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kymol-provenance-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root / "A source"
        self.b = self.root / "B source"
        self.a.mkdir()
        self.b.mkdir()
        self.pdb_a = self.a / "synthetic.pdb"
        self.pdb_b = self.b / "synthetic.pdb"
        self.pdb_a.write_text(PDB)
        self.pdb_b.write_text(PDB.replace("2.000", "3.000"))
        self.original_hashes = [hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (self.pdb_a, self.pdb_b)]
        self.pm = pymol2.PyMOL()
        self.pm.start()
        self.addCleanup(self.pm.stop)
        self.cmd = self.pm.cmd
        self.tracker = get_tracker(self.cmd)
        self.tracker.install()
        self.addCleanup(self.tracker.uninstall)

    def tearDown(self):
        self.assertEqual(self.original_hashes, [hashlib.sha256(p.read_bytes()).hexdigest()
                                               for p in (self.pdb_a, self.pdb_b)])

    def test_api_and_command_load_record_actual_folders(self):
        self.cmd.load(str(self.pdb_a), "unrelated_model_name")
        self.assertEqual(self.tracker.record_for("unrelated_model_name").paths, (str(self.pdb_a),))
        self.cmd.do('load "{}", command_model'.format(str(self.pdb_b).replace("\\", "/")))
        self.assertEqual(self.tracker.record_for("command_model").paths, (str(self.pdb_b),))
        self.assertEqual(self.tracker.export_default("command_model", "cif").directory, str(self.b))

    def test_default_object_name_and_append_multi_directory(self):
        self.cmd.load(str(self.pdb_a))
        self.assertTrue(self.tracker.record_for("synthetic").complete)
        self.cmd.load(str(self.pdb_b), "synthetic", state=0)
        record = self.tracker.record_for("synthetic")
        self.assertEqual(set(record.paths), {str(self.pdb_a), str(self.pdb_b)})
        self.assertEqual(self.cmd.count_states("synthetic"), 2)
        self.assertTrue(self.tracker.export_default("synthetic", "pdb").used_fallback)

    def test_rename_group_session_reload_and_name_reuse(self):
        self.cmd.load(str(self.pdb_a), "original")
        self.cmd.set_name("original", "renamed")
        self.cmd.group("folder", "renamed")
        self.assertEqual(self.tracker.record_for("renamed").paths, (str(self.pdb_a),))
        session = self.root / "saved_session.pse"
        self.cmd.save(str(session))
        self.cmd.reinitialize()
        self.cmd.load(str(session))
        self.assertEqual(self.tracker.record_for("renamed").paths, (str(self.pdb_a),))
        self.assertNotIn(str(session), self.tracker.record_for("renamed").paths)
        self.cmd.delete("renamed")
        self.cmd.read_pdbstr(PDB, "renamed")
        self.assertEqual(self.tracker.record_for("renamed"), SourceRecord())

    def test_copy_and_cut_inherit_captured_source_metadata(self):
        self.cmd.load(str(self.pdb_a), "source_obj")
        captured = self.tracker.capture(["source_obj"])
        self.cmd.create("copy", "source_obj and chain A")
        self.tracker.apply("copy", captured)
        self.cmd.extract("cut", "source_obj and chain B")
        self.tracker.apply("cut", captured)
        for name in ("source_obj", "copy", "cut"):
            self.assertEqual(self.tracker.record_for(name).paths, (str(self.pdb_a),))

    def test_preexisting_unknown_append_remains_incomplete(self):
        self.cmd.read_pdbstr(PDB, "existing")
        self.cmd.load(str(self.pdb_a), "existing")
        record = self.tracker.record_for("existing")
        self.assertEqual(record.paths, (str(self.pdb_a),))
        self.assertFalse(record.complete)

    def test_memory_append_marks_file_provenance_incomplete(self):
        for method, args in (
            ("read_pdbstr", (PDB, "tracked")),
            ("load_raw", (PDB, "pdb", "tracked")),
        ):
            with self.subTest(method=method):
                self.cmd.delete("all")
                self.cmd.load(str(self.pdb_a), "tracked")
                self.assertTrue(self.tracker.record_for("tracked").complete)
                getattr(self.cmd, method)(*args)
                self.assertEqual(self.cmd.count_states("tracked"), 2)
                record = self.tracker.record_for("tracked")
                self.assertEqual(record.paths, (str(self.pdb_a),))
                self.assertFalse(record.complete)
                self.assertTrue(self.tracker.export_default("tracked", "pdb").used_fallback)

    def test_file_load_after_memory_append_remains_partial(self):
        self.cmd.load(str(self.pdb_a), "tracked")
        self.cmd.read_pdbstr(PDB, "tracked")
        self.cmd.load(str(self.pdb_b), "tracked")
        self.assertFalse(self.tracker.record_for("tracked").complete)

    def test_native_undo_redo_preserves_copy_and_rename_provenance(self):
        self.cmd.undo_enable()  # Isolated test instance only; user settings are untouched.
        self.cmd.load(str(self.pdb_a), "source_obj")
        with self.cmd.UndoSessionCM("copy and source metadata"):
            record = self.tracker.capture(["source_obj"])
            self.cmd.create("copied", "source_obj and chain A")
            self.tracker.apply("copied", record)
        self.cmd.undo()
        self.assertNotIn("copied", self.cmd.get_names_of_type("object:molecule"))
        self.cmd.redo()
        self.assertEqual(self.tracker.record_for("copied").paths, (str(self.pdb_a),))
        with self.cmd.UndoSessionCM("rename metadata owner"):
            self.cmd.set_name("copied", "renamed_copy")
        self.cmd.undo()
        self.assertEqual(self.tracker.record_for("copied").paths, (str(self.pdb_a),))
        self.cmd.redo()
        self.assertEqual(self.tracker.record_for("renamed_copy").paths, (str(self.pdb_a),))

    def test_cif_export_and_reload_have_new_file_provenance(self):
        self.cmd.load(str(self.pdb_a), "source_obj")
        suggestion = self.tracker.export_default("source_obj", "cif")
        self.cmd.save(suggestion.path, "source_obj", format="cif")
        self.cmd.load(suggestion.path, "from_cif")
        self.assertEqual(self.tracker.record_for("from_cif").paths, (suggestion.path,))
        self.assertEqual(self.cmd.count_atoms("from_cif"), 2)

    def test_reserved_name_follows_native_naming_rule(self):
        self.cmd.load(str(self.pdb_a), "model")
        self.cmd.load(str(self.pdb_b), "model")
        actual = self.cmd.get_legal_name("model")
        self.assertEqual(set(self.tracker.record_for(actual).paths),
                         {str(self.pdb_a), str(self.pdb_b)})

    def test_failed_load_preserves_metadata_and_hook_restores_exact_entries(self):
        self.cmd.load(str(self.pdb_a), "source_obj")
        prior = self.tracker.record_for("source_obj")
        with self.assertRaises(Exception):
            self.cmd.load(str(self.root / "missing.pdb"), "source_obj")
        self.assertEqual(prior, self.tracker.record_for("source_obj"))
        self.tracker.uninstall()
        api, parser = self.cmd.load, self.cmd.keyword["load"]
        self.tracker.install()
        self.tracker.install()
        self.tracker.uninstall()
        self.assertIs(self.cmd.load, api)
        self.assertIs(self.cmd.keyword["load"], parser)


if __name__ == "__main__":
    unittest.main()
