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

    def get_names_of_type(self, kind):
        self.calls.append(("get_names_of_type", kind))
        if kind == "object:group":
            return list(self.groups)
        return self.objects

    def get_object_list(self, selection):
        self.calls.append(("get_object_list", selection))
        return self.sele_objects

    def get_names(self, kind="all", selection=""):
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
        return self.selection_atoms if "sele" in selection else 12

    def super(self, mobile, target):
        self.calls.append(("super", mobile, target))
        return (1.0, 12)

    def align(self, mobile, target):
        self.calls.append(("align", mobile, target))
        return (1.0, 12)

    def cealign(self, target, mobile):
        self.calls.append(("cealign", target, mobile))
        return {"RMSD": 1.0}

    def color(self, color, selection):
        self.calls.append(("color", color, selection))

    def save(self, filename, selection, format):
        self.calls.append(("save", filename, selection, format))

    def get_fastastr(self, selection):
        self.calls.append(("get_fastastr", selection))
        return ">{}\nACDE\n".format(selection)

    def delete(self, object_name):
        self.calls.append(("delete", object_name))
        self.objects.remove(object_name)

    def enable(self, object_name):
        self.calls.append(("enable", object_name))

    def disable(self, object_name):
        self.calls.append(("disable", object_name))

    def orient(self, selection):
        self.calls.append(("orient", selection))

    def set_name(self, old_name, new_name):
        self.calls.append(("set_name", old_name, new_name))
        index = self.objects.index(old_name)
        self.objects[index] = new_name
        self.chains[new_name] = self.chains.pop(old_name)


class KYMolControllerTests(unittest.TestCase):
    def setUp(self):
        self.cmd = FakeCmd()
        self.messages = []
        self.controller = KYMolController(self.cmd, self.messages.append)

    def test_sync_uses_selection_and_last_item_as_initial_active(self):
        state = self.controller.sync_from_pymol_selection()
        self.assertEqual(["ref", "pose1"], state.selected)
        self.assertEqual("pose1", state.active)

    def test_align_auto_falls_back_to_shared_chain_ca_atoms(self):
        self.controller.set_selection(["ref", "pose1", "pose2"], active="ref")
        self.controller.align_selected(method="super", scope="auto")
        calls = [call for call in self.cmd.calls if call[0] == "super"]
        self.assertEqual(2, len(calls))
        self.assertIn("pose1 and chain A", calls[0][1])
        self.assertIn("ref and chain A", calls[0][2])

    def test_cealign_reverses_api_argument_order(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.controller.align_selected(method="cealign", scope="common_chain")
        call = [call for call in self.cmd.calls if call[0] == "cealign"][0]
        self.assertIn("ref and chain A", call[1])
        self.assertIn("pose1 and chain A", call[2])

    def test_color_selected_matches_pymol_by_chain_cycle(self):
        self.controller.set_selection(["ref", "pose1"], active="ref")
        self.controller.color_selected_by_chain()
        calls = [call for call in self.cmd.calls if call[0] == "color"]
        self.assertEqual([26, 5, 154], [call[1] for call in calls])
        self.assertEqual(3, len(calls))
        self.assertIn("chain A", calls[0][2])
        self.assertIn("model ref", calls[0][2])
        self.assertIn("model pose1", calls[0][2])

    def test_export_prefers_pymol_selection_unless_whole_object_requested(self):
        self.controller.set_selection(["ref"], active="ref")
        self.cmd.selection_atoms = 4
        self.controller.export_active("x.cif", "cif")
        self.assertEqual(("save", "x.cif", "(ref and sele)", "cif"), self.cmd.calls[-1])
        self.controller.export_active("x.pdb", "pdb", whole_chain=True, chain="A")
        self.assertEqual(("save", "x.pdb", "(ref and chain A)", "pdb"), self.cmd.calls[-1])

    def test_alignment_requires_multiple_objects(self):
        self.controller.set_selection(["ref"], active="ref")
        with self.assertRaises(KYMolError):
            self.controller.align_selected()

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

    def test_panel_display_modes_control_the_pymol_view(self):
        self.controller.set_selection(["pose1", "pose2"], active="pose2")
        self.controller.display_selected("only")
        self.assertIn(("disable", "all"), self.cmd.calls)
        self.assertIn(("enable", "pose1"), self.cmd.calls)
        self.assertIn(("enable", "pose2"), self.cmd.calls)
        self.controller.focus_active()
        self.assertEqual(("orient", "pose2"), self.cmd.calls[-1])

    def test_show_all_objects_reveals_every_molecular_object(self):
        shown = self.controller.show_all_objects()
        self.assertEqual(["ref", "pose1", "pose2"], shown)
        self.assertEqual(
            [("enable", "ref"), ("enable", "pose1"), ("enable", "pose2")],
            [call for call in self.cmd.calls if call[0] == "enable"],
        )

    def test_rename_active_updates_pymol_and_panel_state(self):
        self.controller.set_selection(["ref", "pose1"], active="pose1")
        renamed = self.controller.rename_active("candidate_001")
        self.assertEqual("candidate_001", renamed)
        self.assertIn(("set_name", "pose1", "candidate_001"), self.cmd.calls)
        self.assertEqual(["ref", "candidate_001"], self.controller.state.selected)
        self.assertEqual("candidate_001", self.controller.state.active)

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

        self.cmd.calls.clear()
        self.controller.display_group("P1", "only")
        self.assertEqual(
            [("disable", "all"), ("enable", "pose1"), ("enable", "pose2")],
            [call for call in self.cmd.calls if call[0] in ("disable", "enable")],
        )


if __name__ == "__main__":
    unittest.main()
