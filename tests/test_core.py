import copy
import unittest

from KYMol.core import KYMolController, KYMolError


class FakeCmd:
    def __init__(self):
        self.objects = ["ref", "pose1", "pose2"]
        self.chains = {"ref": ["A", "B"], "pose1": ["A", "C"], "pose2": ["A"]}
        self.calls = []
        self.sele_objects = ["ref", "pose1"]
        self.selection_atoms = 0
        self.groups = {}
        self.enabled = set(self.objects)
        self.transforms = {name: 0 for name in self.objects}
        self.colors = {}
        self.focused = None
        self.atom_visuals = {
            ("ref", "A"): [(3, 32), (3, 32)],
            ("ref", "B"): [(5, 32), (5, 32)],
            ("pose1", "A"): [(3, 32)],
            ("pose1", "C"): [(6, 32)],
            ("pose2", "A"): [(3, 32)],
        }
        self.color_tuples = {
            3: (0.0, 1.0, 0.0),
            5: (0.0, 0.0, 1.0),
            6: (1.0, 1.0, 0.0),
        }
        self.sequences = {
            ("ref", "A"): "AAAAAA",
            ("ref", "B"): "CCCCCC",
            ("pose1", "A"): "AAAACC",
            ("pose1", "C"): "CCCCCT",
            ("pose2", "A"): "AAAATA",
        }
        self._undo_stack = []
        self._redo_stack = []

    class _UndoSession:
        def __init__(self, owner, label):
            self.owner = owner
            self.label = label

        def __enter__(self):
            self.before = self.owner._snapshot()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            if exc_type is None:
                self.owner._undo_stack.append(
                    (self.label, self.before, self.owner._snapshot())
                )
                self.owner._redo_stack.clear()

    def _snapshot(self):
        return {
            "objects": copy.deepcopy(self.objects),
            "chains": copy.deepcopy(self.chains),
            "groups": copy.deepcopy(self.groups),
            "enabled": copy.deepcopy(self.enabled),
            "transforms": copy.deepcopy(self.transforms),
            "colors": copy.deepcopy(self.colors),
            "focused": self.focused,
        }

    def _restore(self, snapshot):
        self.objects = copy.deepcopy(snapshot["objects"])
        self.chains = copy.deepcopy(snapshot["chains"])
        self.groups = copy.deepcopy(snapshot["groups"])
        self.enabled = copy.deepcopy(snapshot["enabled"])
        self.transforms = copy.deepcopy(snapshot["transforms"])
        self.colors = copy.deepcopy(snapshot["colors"])
        self.focused = snapshot["focused"]

    def UndoSessionCM(self, label):
        return self._UndoSession(self, label)

    def undo_current_undo_redo(self):
        undo_label = self._undo_stack[-1][0] if self._undo_stack else ""
        redo_label = self._redo_stack[-1][0] if self._redo_stack else ""
        return undo_label, redo_label

    def undo(self):
        label, before, after = self._undo_stack.pop()
        self._restore(before)
        self._redo_stack.append((label, before, after))

    def redo(self):
        label, before, after = self._redo_stack.pop()
        self._restore(after)
        self._undo_stack.append((label, before, after))

    def get_names_of_type(self, kind):
        self.calls.append(("get_names_of_type", kind))
        if kind == "object:group":
            return list(self.groups)
        return self.objects

    def get_legal_name(self, name):
        reserved = {"x", "y", "chain", "all", "none"}
        return "{}_".format(name) if name in reserved else name

    def get_object_list(self, selection):
        self.calls.append(("get_object_list", selection))
        return self.sele_objects

    def get_names(self, kind="all", selection="", enabled_only=0):
        if kind == "objects" and enabled_only:
            return [name for name in self.objects if name in self.enabled]
        if kind == "all":
            return list(self.objects) + list(self.groups)
        if kind == "objects" and selection.startswith("?"):
            return list(self.groups.get(selection[1:], []))
        return list(self.objects)

    def group(self, group_name, members="", action="auto"):
        member_names = members.split()
        self.calls.append(("group", group_name, members, action))
        self.groups.setdefault(group_name, [])
        if action in ("add", "auto"):
            for member in member_names:
                for existing_members in self.groups.values():
                    if member in existing_members:
                        existing_members.remove(member)
                if member not in self.groups[group_name]:
                    self.groups[group_name].append(member)

    def get_chains(self, object_name):
        if object_name.startswith("("):
            chains = []
            for name in self.objects:
                if name in object_name:
                    for chain in self.chains[name]:
                        if chain not in chains:
                            chains.append(chain)
            return chains
        return self.chains[object_name]

    def count_atoms(self, selection):
        # No current structural selection in this fixture.
        return self.selection_atoms if "sele" in selection else 20

    def iterate(self, selection, expression, space):
        for (object_name, chain), rows in self.atom_visuals.items():
            if 'model "{}"'.format(object_name) not in selection:
                continue
            for color, reps in rows:
                space["rows"].append((object_name, chain, color, reps))

    def get_color_tuple(self, color_index):
        return self.color_tuples[color_index]

    def super(self, mobile, target):
        self.calls.append(("super", mobile, target))
        self._mark_aligned(mobile)
        return (1.0, 12)

    def align(self, mobile, target):
        self.calls.append(("align", mobile, target))
        self._mark_aligned(mobile)
        return (1.0, 12)

    def cealign(self, target, mobile):
        self.calls.append(("cealign", target, mobile))
        self._mark_aligned(mobile)
        return {"RMSD": 1.0}

    def _mark_aligned(self, mobile_selection):
        for name in self.objects:
            if (
                "model {}".format(name) in mobile_selection
                or 'model "{}"'.format(name) in mobile_selection
            ):
                self.transforms[name] += 1
                return

    def color(self, color, selection):
        self.calls.append(("color", color, selection))
        self.colors[selection] = color

    def save(self, filename, selection, format):
        self.calls.append(("save", filename, selection, format))

    def get_fastastr(self, selection):
        self.calls.append(("get_fastastr", selection))
        for (object_name, chain), sequence in self.sequences.items():
            model_matches = (
                "model {}".format(object_name) in selection
                or 'model "{}"'.format(object_name) in selection
            )
            chain_matches = (
                "chain {}".format(chain) in selection
                or 'chain "{}"'.format(chain) in selection
            )
            if model_matches and chain_matches:
                return ">{}_{}\n{}\n".format(object_name, chain, sequence)
        return ">{}\nACDE\n".format(selection)

    def delete(self, object_name):
        self.calls.append(("delete", object_name))
        self.objects.remove(object_name)

    def enable(self, object_name):
        self.calls.append(("enable", object_name))
        self.enabled.add(object_name)

    def disable(self, object_name):
        self.calls.append(("disable", object_name))
        if object_name == "all":
            self.enabled.clear()
        else:
            self.enabled.discard(object_name)

    def orient(self, selection):
        self.calls.append(("orient", selection))
        self.focused = selection

    def set_name(self, old_name, new_name):
        self.calls.append(("set_name", old_name, new_name))
        index = self.objects.index(old_name)
        self.objects[index] = new_name
        self.chains[new_name] = self.chains.pop(old_name)

    def _chains_from_selection(self, selection):
        source = next(name for name in self.objects if '"{}"'.format(name) in selection)
        chains = [
            chain
            for chain in self.chains[source]
            if 'chain "{}"'.format(chain) in selection
        ]
        return source, chains

    def create(self, name, selection, **kwargs):
        self.calls.append(("create", name, selection))
        source, chains = self._chains_from_selection(selection)
        self.objects.append(name)
        self.chains[name] = list(chains)
        self.enabled.add(name)

    def extract(self, name, selection, **kwargs):
        self.calls.append(("extract", name, selection))
        source, chains = self._chains_from_selection(selection)
        self.objects.append(name)
        self.chains[name] = list(chains)
        self.chains[source] = [
            chain for chain in self.chains[source] if chain not in chains
        ]
        self.enabled.add(name)


class KYMolControllerTests(unittest.TestCase):
    def setUp(self):
        self.cmd = FakeCmd()
        self.messages = []
        self.controller = KYMolController(self.cmd, self.messages.append)

    def test_sync_uses_selection_and_last_item_as_initial_active(self):
        state = self.controller.sync_from_pymol_selection()
        self.assertEqual(["ref", "pose1"], state.selected)
        self.assertEqual("pose1", state.active)

    def test_chain_visual_state_uses_the_actual_pymol_atom_color(self):
        states = self.controller.chain_visual_states(["ref"])

        self.assertEqual("#00ff00", states[("ref", "A")].color_hex)

    def test_chain_visual_state_reports_hidden_representations_and_disabled_objects(self):
        self.cmd.atom_visuals[("ref", "A")] = [(3, 0), (3, 0)]
        states = self.controller.chain_visual_states(["ref"])
        self.assertTrue(states[("ref", "A")].hidden)
        self.assertFalse(states[("ref", "B")].hidden)

        self.cmd.enabled.remove("ref")
        states = self.controller.chain_visual_states(["ref"])
        self.assertTrue(states[("ref", "B")].hidden)

    def test_default_alignment_independently_uses_each_mobiles_best_target_chain(self):
        self.cmd.chains["pose1"] = ["C"]
        self.controller.set_selection(["ref", "pose1", "pose2"], active="ref")
        self.controller.align_selected()
        calls = [call for call in self.cmd.calls if call[0] == "align"]
        self.assertEqual(2, len(calls))
        self.assertIn('model "pose1" and chain "C"', calls[0][1])
        self.assertIn('model "ref" and chain "B"', calls[0][2])
        self.assertIn('model "pose2" and chain "A"', calls[1][1])
        self.assertIn('model "ref" and chain "A"', calls[1][2])
        self.assertFalse([call for call in self.cmd.calls if call[0] == "super"])

    def test_alignment_of_multiple_mobile_objects_is_undone_as_one_action(self):
        self.controller.set_selection(["ref", "pose1", "pose2"], active="ref")
        self.controller.align_selected()
        self.assertEqual(1, self.cmd.transforms["pose1"])
        self.assertEqual(1, self.cmd.transforms["pose2"])

        self.controller.undo()

        self.assertEqual(0, self.cmd.transforms["pose1"])
        self.assertEqual(0, self.cmd.transforms["pose2"])

    def test_alignment_quotes_blank_chain_identifiers(self):
        self.cmd.chains["pose2"] = [""]
        self.cmd.sequences[("pose2", "")] = "AAAAAA"
        self.controller.set_selection(["ref", "pose2"], active="ref")

        self.controller.align_selected()

        call = [call for call in self.cmd.calls if call[0] == "align"][-1]
        self.assertIn('model "pose2" and chain ""', call[1])

    def test_cealign_reverses_api_argument_order(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.controller.align_selected(method="cealign", scope="common_chain")
        call = [call for call in self.cmd.calls if call[0] == "cealign"][0]
        self.assertIn('model "ref" and chain "A"', call[1])
        self.assertIn('model "pose1" and chain "A"', call[2])

    def test_color_selected_matches_pymol_by_chain_cycle(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.controller.color_selected_by_chain()
        calls = [call for call in self.cmd.calls if call[0] == "color"]
        self.assertEqual([26, 5, 154], [call[1] for call in calls])
        self.assertEqual(3, len(calls))
        self.assertIn('chain "A"', calls[0][2])
        self.assertIn('model "ref"', calls[0][2])
        self.assertIn('model "pose1"', calls[0][2])

    def test_chain_coloring_is_undoable(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.controller.color_selected_by_chain()
        self.assertTrue(self.cmd.colors)

        self.controller.undo()

        self.assertEqual({}, self.cmd.colors)

    def test_export_prefers_pymol_selection_unless_whole_object_requested(self):
        self.controller.set_selection(["ref"], active="ref")
        self.cmd.selection_atoms = 4
        self.controller.export_active("x.cif", "cif")
        self.assertEqual(("save", "x.cif", '(model "ref" and ?sele)', "cif"), self.cmd.calls[-1])
        self.controller.export_active("x.pdb", "pdb", whole_chain=True, chain="A")
        self.assertEqual(("save", "x.pdb", '(model "ref" and chain "A")', "pdb"), self.cmd.calls[-1])

    def test_alignment_requires_multiple_objects(self):
        self.controller.set_selection(["ref"], active="ref")
        with self.assertRaises(KYMolError):
            self.controller.align_selected()

    def test_auto_alignment_rejects_missing_requested_target_chain(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        with self.assertRaisesRegex(KYMolError, "No protein chain pair"):
            self.controller.align_selected(chain="Z")
        self.assertFalse([call for call in self.cmd.calls if call[0] == "align"])

    def test_alignment_preflights_all_mobiles_before_moving_any(self):
        self.cmd.chains["pose2"] = ["Z"]
        self.controller.set_selection(["ref", "pose1", "pose2"], active="ref")
        with self.assertRaises(KYMolError):
            self.controller.align_selected(scope="common_chain")
        self.assertEqual(0, self.cmd.transforms["pose1"])

    def test_cealign_rejects_short_selection_before_running_engine(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.cmd.count_atoms = lambda selection: 12
        with self.assertRaisesRegex(KYMolError, "16 protein CA"):
            self.controller.align_selected(method="cealign")
        self.assertFalse([call for call in self.cmd.calls if call[0] == "cealign"])

    def test_alignment_rejects_stale_mobile_selection(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.cmd.objects.remove("pose1")
        with self.assertRaisesRegex(KYMolError, "no longer exists"):
            self.controller.align_selected()

    def test_common_chain_alignment_supports_blank_chain_ids(self):
        self.cmd.chains["pose1"] = [""]
        self.cmd.chains["ref"] = [""]
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.controller.align_selected(scope="common_chain")
        call = [call for call in self.cmd.calls if call[0] == "align"][-1]
        self.assertIn('chain ""', call[1])

    def test_invalid_active_object_does_not_pollute_selection(self):
        self.controller.set_selection(["ref"], active="ref")
        with self.assertRaises(KYMolError):
            self.controller.set_active("missing")
        self.assertEqual(["ref"], self.controller.state.selected)
        self.assertEqual("ref", self.controller.state.active)

    def test_chain_copy_rejects_missing_chain_before_partial_copy(self):
        with self.assertRaisesRegex(KYMolError, "no longer exists"):
            self.controller.copy_chains({"ref": ["A", "missing"]})
        self.assertFalse([call for call in self.cmd.calls if call[0] == "create"])

    def test_auto_chain_matching_reads_each_sequence_once_per_batch(self):
        self.controller.set_selection(["ref", "pose1", "pose2"], active="ref")
        self.controller.align_selected()
        reads = [call[1] for call in self.cmd.calls if call[0] == "get_fastastr"]
        self.assertEqual(len(reads), len(set(reads)))

    def test_alignment_report_does_not_call_heuristic_ratio_identity(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.controller.align_selected()
        self.assertFalse(any("identity" in message for message in self.messages))

    def test_automatic_chain_ties_are_reported_without_inventing_mapping(self):
        self.cmd.sequences[("ref", "B")] = self.cmd.sequences[("ref", "A")]
        self.controller.set_selection(["ref", "pose2"], active="ref")
        self.controller.align_selected()
        self.assertTrue(any("Ambiguous automatic chain match: 2 pairs" in message
                            for message in self.messages))

    def test_long_low_alphabet_sequences_keep_matching_with_autojunk_disabled(self):
        # A one-position shift with a different leading residue makes default
        # difflib autojunk discard all popular residue anchors at length >= 200.
        sequence = "ACDEFGHIKLMNPQRSTVWY" * 20
        self.cmd.sequences[("ref", "A")] = sequence
        self.cmd.sequences[("ref", "B")] = "W" * len(sequence)
        self.cmd.sequences[("pose2", "A")] = "Y" + sequence[:-1]
        pair = self.controller._best_sequence_chain_pair("pose2", "ref")
        self.assertEqual(("A", "A"), pair[:2])
        self.assertGreater(pair[2], 0.99)

    def test_delete_selected_removes_objects_and_clears_panel_state(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        deleted = self.controller.delete_selected()
        self.assertEqual(["pose1", "pose2"], deleted)
        self.assertEqual(
            [("delete", "pose1"), ("delete", "pose2")],
            [call for call in self.cmd.calls if call[0] == "delete"],
        )
        self.assertEqual([], self.controller.state.selected)
        self.assertIsNone(self.controller.state.active)

    def test_deleted_objects_and_selection_are_restored_by_undo(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        self.controller.delete_selected()

        self.controller.undo()

        self.assertEqual(["ref", "pose1", "pose2"], self.cmd.objects)
        self.assertEqual(["pose1", "pose2"], self.controller.state.selected)
        self.assertEqual("pose2", self.controller.state.active)

    def test_copying_selected_chains_creates_a_named_object_and_is_undoable(self):
        created = self.controller.copy_chains({"ref": ["B"]})

        self.assertEqual(["ref_B_copy"], created)
        self.assertEqual(["B"], self.cmd.chains["ref_B_copy"])
        self.assertEqual(["ref_B_copy"], self.controller.state.selected)
        self.assertEqual("ref_B_copy", self.controller.state.active)

        self.controller.undo()
        self.assertNotIn("ref_B_copy", self.cmd.objects)

    def test_cutting_selected_chains_moves_them_to_a_custom_named_object(self):
        created = self.controller.cut_chains(
            {"ref": ["A"]}, requested_name="il13_m1_A"
        )

        self.assertEqual(["il13_m1_A"], created)
        self.assertEqual(["B"], self.cmd.chains["ref"])
        self.assertEqual(["A"], self.cmd.chains["il13_m1_A"])

        self.controller.undo()
        self.assertEqual(["A", "B"], self.cmd.chains["ref"])
        self.assertNotIn("il13_m1_A", self.cmd.objects)

    def test_panel_display_modes_control_the_pymol_view(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        self.controller.display_selected("only")
        self.assertIn(("disable", "all"), self.cmd.calls)
        self.assertIn(("enable", "pose1"), self.cmd.calls)
        self.assertIn(("enable", "pose2"), self.cmd.calls)
        self.controller.focus_active()
        self.assertEqual(("orient", "pose2"), self.cmd.calls[-1])

    def test_focus_active_is_undoable(self):
        self.cmd.orient("ref")
        self.controller.set_selection(["pose2"], active="pose2")
        self.controller.focus_active()
        self.assertEqual("pose2", self.cmd.focused)

        self.controller.undo()

        self.assertEqual("ref", self.cmd.focused)

    def test_only_selected_display_mode_is_undoable(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        self.controller.display_selected("only")
        self.assertEqual({"pose1", "pose2"}, self.cmd.enabled)

        self.controller.undo()

        self.assertEqual({"ref", "pose1", "pose2"}, self.cmd.enabled)

    def test_visibility_toggle_hides_visible_selection_then_shows_it_again(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        self.controller.toggle_selected_visibility()
        self.assertEqual({"ref"}, self.cmd.enabled)
        self.controller.toggle_selected_visibility()
        self.assertEqual({"ref", "pose1", "pose2"}, self.cmd.enabled)

    def test_visibility_change_is_undoable_in_one_step(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        self.controller.toggle_selected_visibility()

        self.controller.undo()

        self.assertEqual({"ref", "pose1", "pose2"}, self.cmd.enabled)

    def test_show_all_objects_reveals_every_molecular_object(self):
        shown = self.controller.show_all_objects()
        self.assertEqual(["ref", "pose1", "pose2"], shown)
        self.assertEqual(
            [("enable", "ref"), ("enable", "pose1"), ("enable", "pose2")],
            [call for call in self.cmd.calls if call[0] == "enable"],
        )

    def test_show_all_can_be_undone_to_the_previous_visibility(self):
        self.cmd.disable("pose2")
        self.controller.show_all_objects()
        self.assertIn("pose2", self.cmd.enabled)

        self.controller.undo()

        self.assertNotIn("pose2", self.cmd.enabled)

    def test_rename_active_updates_pymol_and_panel_state(self):
        self.controller.set_selection(["ref", "pose1"], active="pose1")
        renamed = self.controller.rename_active("candidate_001")
        self.assertEqual("candidate_001", renamed)
        self.assertIn(("set_name", "pose1", "candidate_001"), self.cmd.calls)
        self.assertEqual(["ref", "candidate_001"], self.controller.state.selected)
        self.assertEqual("candidate_001", self.controller.state.active)

    def test_rename_rejects_pymol_reserved_names_with_a_safe_suggestion(self):
        self.controller.set_selection(["pose1"], active="pose1")

        with self.assertRaisesRegex(KYMolError, "Try 'x_'"):
            self.controller.rename_active("x")

        self.assertIn("pose1", self.cmd.objects)

    def test_undo_and_redo_restore_renamed_object_and_active_selection(self):
        self.controller.set_selection(["ref", "pose1"], active="pose1")
        self.controller.rename_active("candidate_001")

        self.controller.undo()
        self.assertEqual(["ref", "pose1", "pose2"], self.cmd.objects)
        self.assertEqual(["ref", "pose1"], self.controller.state.selected)
        self.assertEqual("pose1", self.controller.state.active)

        self.controller.redo()
        self.assertEqual(["ref", "candidate_001", "pose2"], self.cmd.objects)
        self.assertEqual(
            ["ref", "candidate_001"], self.controller.state.selected
        )
        self.assertEqual("candidate_001", self.controller.state.active)

    def test_empty_undo_and_redo_history_report_a_clear_error(self):
        with self.assertRaisesRegex(KYMolError, "Nothing to undo"):
            self.controller.undo()
        with self.assertRaisesRegex(KYMolError, "Nothing to redo"):
            self.controller.redo()

    def test_create_groups_uses_unique_default_names_and_native_pymol_groups(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        first_group = self.controller.create_group()
        self.assertEqual("P1", first_group)
        self.assertEqual(["pose1", "pose2"], self.cmd.groups["P1"])

        self.controller.set_selection(["ref"], active="ref")
        second_group = self.controller.create_group()
        self.assertEqual("P2", second_group)
        self.assertEqual(["ref"], self.cmd.groups["P2"])

        self.cmd.groups.pop("P1")
        self.assertEqual("P3", self.controller.next_group_name())

        with self.assertRaises(KYMolError):
            self.controller.create_group("P1")

    def test_undoing_group_creation_restores_the_default_group_name(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        self.assertEqual("P1", self.controller.create_group())

        self.controller.undo()

        self.assertNotIn("P1", self.cmd.groups)
        self.assertEqual("P1", self.controller.next_group_name())

    def test_group_members_can_be_selected_hidden_and_isolated(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        self.controller.create_group("P1")
        state = self.controller.select_group("P1")
        self.assertEqual(["pose1", "pose2"], state.selected)

        self.cmd.calls.clear()
        self.controller.display_group("P1", "hide")
        self.assertEqual(
            [("disable", "pose1"), ("disable", "pose2")],
            [call for call in self.cmd.calls if call[0] == "disable"],
        )
        self.controller.undo()
        self.assertEqual({"ref", "pose1", "pose2"}, self.cmd.enabled)

        self.cmd.calls.clear()
        self.controller.display_group("P1", "only")
        self.assertEqual(
            [("disable", "all"), ("enable", "pose1"), ("enable", "pose2")],
            [call for call in self.cmd.calls if call[0] in ("disable", "enable")],
        )

    def test_moving_an_object_into_a_group_is_undoable(self):
        self.controller.set_selection(["pose1"], active="pose1")
        self.controller.create_group("P1")
        self.controller.assign_objects_to_group(["pose2"], "P1")
        self.assertEqual(["pose1", "pose2"], self.cmd.groups["P1"])

        self.controller.undo()

        self.assertEqual(["pose1"], self.cmd.groups["P1"])


if __name__ == "__main__":
    unittest.main()
