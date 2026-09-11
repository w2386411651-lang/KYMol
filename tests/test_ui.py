import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pymol.Qt import QtCore, QtGui, QtWidgets
from PyQt5 import QtTest

from KYMol.core import KYMolController
from KYMol.ui import KYMolDialog


GOLD = "#c99b12"


class FakeCmd:
    def __init__(self):
        self.objects = ["model_1", "model_2", "model_3"]
        self.chains = {
            "model_1": ["A", "B"],
            "model_2": ["A", "C"],
            "model_3": ["D"],
        }
        self.calls = []
        self.groups = {}
        self.enabled = set(self.objects)
        self.atom_visuals = {
            ("model_1", "A"): [(3, 32), (3, 32)],
            ("model_1", "B"): [(5, 0), (5, 0)],
            ("model_2", "A"): [(3, 32)],
            ("model_2", "C"): [(6, 32)],
            ("model_3", "D"): [(7, 32)],
        }
        self.color_tuples = {
            3: (0.0, 1.0, 0.0),
            5: (0.0, 0.0, 1.0),
            6: (1.0, 1.0, 0.0),
            7: (1.0, 0.0, 0.0),
        }
        self._undo_stack = []
        self._redo_stack = []

    class _UndoSession:
        def __init__(self, owner, label):
            self.owner = owner
            self.label = label

        def __enter__(self):
            self.before = self.owner._snapshot()

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
        }

    def _restore(self, snapshot):
        self.objects = copy.deepcopy(snapshot["objects"])
        self.chains = copy.deepcopy(snapshot["chains"])
        self.groups = copy.deepcopy(snapshot["groups"])
        self.enabled = copy.deepcopy(snapshot["enabled"])

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

    def get_names_of_type(self, object_type):
        if object_type == "object:group":
            return list(self.groups)
        return self.objects

    def get_names(self, kind="all", selection="", enabled_only=0):
        if kind == "objects" and enabled_only:
            return [name for name in self.objects if name in self.enabled]
        if kind == "all":
            return list(self.objects) + list(self.groups)
        if kind == "objects" and selection.startswith("?"):
            return list(self.groups.get(selection[1:], []))
        return list(self.objects)

    def delete(self, object_name):
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

    def orient(self, object_name):
        self.calls.append(("orient", object_name))

    def group(self, group_name, members="", action="auto"):
        self.groups.setdefault(group_name, [])
        for member in members.split():
            for group_members in self.groups.values():
                if member in group_members:
                    group_members.remove(member)
            self.groups[group_name].append(member)

    def set_name(self, old_name, new_name):
        self.objects[self.objects.index(old_name)] = new_name
        self.chains[new_name] = self.chains.pop(old_name)
        for group_members in self.groups.values():
            if old_name in group_members:
                group_members[group_members.index(old_name)] = new_name

    def get_chains(self, object_name):
        return list(self.chains[object_name])

    def iterate(self, selection, expression, space):
        for (object_name, chain), rows in self.atom_visuals.items():
            if 'model "{}"'.format(object_name) not in selection:
                continue
            for color, reps in rows:
                space["rows"].append((object_name, chain, color, reps))

    def get_color_tuple(self, color_index):
        return self.color_tuples[color_index]

    def _chains_from_selection(self, selection):
        source = next(name for name in self.objects if '"{}"'.format(name) in selection)
        chains = [
            chain
            for chain in self.chains[source]
            if 'chain "{}"'.format(chain) in selection
        ]
        return source, chains

    def create(self, name, selection, **kwargs):
        source, chains = self._chains_from_selection(selection)
        self.calls.append(("create", name, selection))
        self.objects.append(name)
        self.chains[name] = list(chains)
        self.enabled.add(name)

    def extract(self, name, selection, **kwargs):
        source, chains = self._chains_from_selection(selection)
        self.calls.append(("extract", name, selection))
        self.objects.append(name)
        self.chains[name] = list(chains)
        self.chains[source] = [
            chain for chain in self.chains[source] if chain not in chains
        ]
        self.enabled.add(name)


class KYMolDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_default_chain_controls_fit_in_small_resizable_panel(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        self.addCleanup(dialog.close)
        dialog.show()
        dialog.resize(540, 400)
        self.app.processEvents()
        self.assertLessEqual(dialog.height(), 420)
        self.assertTrue(dialog.chain_actions.isVisible())
        self.assertFalse(dialog.object_list.isColumnHidden(1))
        self.assertGreaterEqual(dialog.object_list.height(), 96)
        tree_bottom = dialog.object_list.mapTo(dialog, dialog.object_list.rect().bottomLeft()).y()
        actions_top = dialog.chain_actions.mapTo(dialog, QtCore.QPoint()).y()
        self.assertGreater(actions_top, tree_bottom)
        self.assertGreater(dialog.tools_scroll.verticalScrollBar().maximum(), 0)

    def test_opening_panel_keeps_an_existing_controller_selection(self):
        controller = KYMolController(FakeCmd(), reporter=lambda message: None)
        controller.set_selection(["model_1", "model_2"], "model_1")
        dialog = KYMolDialog(controller)
        self.addCleanup(dialog.close)
        self.assertEqual(["model_1", "model_2"], controller.state.selected)
        self.assertEqual("model_1", controller.state.active)
        self.assertEqual("model_1", dialog._current_name())

    def test_search_keyboard_cannot_trigger_chain_operations_or_structure_undo(self):
        fake = FakeCmd()
        controller = KYMolController(fake, reporter=lambda message: None)
        controller.set_selection(["model_1"], "model_1")
        controller.rename_active("model_renamed")
        dialog = KYMolDialog(controller)
        self.addCleanup(dialog.close)
        dialog.show()
        dialog.search_edit.setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClicks(dialog.search_edit, "model")
        self.assertEqual("1 / 3", dialog.search_count.text())
        with patch.object(dialog, "_transform_selected_chains") as transform:
            QtTest.QTest.keyClick(dialog.search_edit, QtCore.Qt.Key_Return)
            self.assertEqual("2 / 3", dialog.search_count.text())
            QtTest.QTest.keyClick(dialog.search_edit, QtCore.Qt.Key_Return, QtCore.Qt.ShiftModifier)
            self.assertEqual("1 / 3", dialog.search_count.text())
            transform.assert_not_called()
        QtTest.QTest.keyClick(dialog.search_edit, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
        self.assertIn("model_renamed", fake.objects)
        self.assertEqual("", dialog.search_edit.text())
        dialog.search_edit.setText("model")
        QtTest.QTest.keyClick(dialog.search_edit, QtCore.Qt.Key_Escape)
        self.assertEqual("", dialog.search_edit.text())
        self.assertTrue(dialog.isVisible())

    def test_search_many_long_names_after_refresh_does_not_scan_atoms(self):
        fake = FakeCmd()
        fake.objects = ["synthetic_result_{:03d}_very_long_model_name".format(index) for index in range(100)]
        fake.chains = {name: ["A"] for name in fake.objects}
        fake.groups = {"batch": fake.objects[:50]}
        dialog = KYMolDialog(KYMolController(fake, reporter=lambda message: None))
        self.addCleanup(dialog.close)
        dialog.chain_visual_timer.stop()
        dialog.show()
        self.app.processEvents()
        dialog.search_edit.setText("099_very_long")
        name = dialog._search_matches[0]
        self.assertEqual(fake.objects[-1], name)
        item = next(item for item in dialog.object_list.object_items() if item.text(0) == name)
        self.assertTrue(dialog.object_list.viewport().rect().intersects(dialog.object_list.visualItemRect(item)))
        self.assertEqual(name, item.toolTip(0))
        with patch.object(fake, "iterate", side_effect=AssertionError("Search must not query atoms")):
            dialog.search_edit.setText("result_")
            dialog._step_search(99)
            self.assertEqual("100 / 100", dialog.search_count.text())
        dialog.refresh_objects(keep_selection=True)
        self.assertEqual("100 / 100", dialog.search_count.text())
        self.assertEqual(100, dialog.object_list.count())

    def test_splitter_changes_list_height_and_keeps_tools_accessible(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        self.addCleanup(dialog.close)
        dialog.resize(820, 760)
        dialog.show()
        self.app.processEvents()
        before = dialog.object_list.height()
        sizes = dialog.content_splitter.sizes()
        dialog.content_splitter.setSizes([sizes[0] + 90, sizes[1] - 90])
        self.app.processEvents()
        self.assertGreater(dialog.object_list.height(), before + 50)
        self.assertTrue(dialog.content_splitter.handle(1).isVisible())
        self.assertGreater(dialog.tools_scroll.height(), 40)

    def test_model_search_expands_groups_and_preserves_selection_active_and_visibility(self):
        fake = FakeCmd()
        fake.groups = {"nested_results": ["model_2", "model_3"]}
        fake.enabled = {"model_1"}
        dialog = KYMolDialog(KYMolController(fake, reporter=lambda message: None))
        self.addCleanup(dialog.close)
        dialog.show()
        items = {item.text(0): item for item in dialog.object_list.object_items()}
        dialog.object_list.select_exclusive(items["model_1"])
        dialog.object_list.topLevelItem(0).setExpanded(False)
        expected = (list(dialog.controller.state.selected), dialog.controller.state.active, set(fake.enabled))
        dialog.search_edit.setText("MODEL_")
        self.app.processEvents()
        self.assertEqual("1 / 3", dialog.search_count.text())
        self.assertTrue(dialog.object_list.topLevelItem(0).isExpanded())
        self.assertIs(dialog.object_list.currentItem(), items["model_1"])
        dialog.search_next_button.click()
        self.assertEqual("2 / 3", dialog.search_count.text())
        dialog.search_previous_button.click()
        self.assertEqual("1 / 3", dialog.search_count.text())
        dialog.search_previous_button.click()
        self.assertEqual("3 / 3", dialog.search_count.text())
        self.assertEqual(expected, (dialog.controller.state.selected, dialog.controller.state.active, fake.enabled))
        dialog.search_edit.setText("missing")
        self.assertEqual("0 / 0", dialog.search_count.text())
        self.assertFalse(dialog.search_next_button.isEnabled())
        self.assertTrue(all(not item.isHidden() for item in dialog.object_list.object_items()))
        dialog.search_edit.clear()
        self.assertEqual(expected, (dialog.controller.state.selected, dialog.controller.state.active, fake.enabled))

    def test_many_long_chain_labels_keep_row_height_and_are_reachable(self):
        fake = FakeCmd()
        fake.chains["model_1"] = ["CHAIN_{:02d}_LONG_LABEL".format(index) for index in range(40)]
        dialog = KYMolDialog(KYMolController(fake, reporter=lambda message: None))
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        heights = [dialog.object_list.visualItemRect(item).height() for item in dialog.object_list.object_items()]
        self.assertEqual(1, len(set(heights)))
        strip = dialog.object_list.itemWidget(dialog.object_list.item(0), 1)
        self.assertGreater(strip.scroll_area.horizontalScrollBar().maximum(), 0)
        button = dialog._chain_buttons[("model_1", fake.chains["model_1"][-1])]
        button.setFocus()
        self.app.processEvents()
        self.assertGreater(strip.scroll_area.horizontalScrollBar().value(), 0)
        self.assertTrue(strip.scroll_area.viewport().rect().intersects(button.rect().translated(button.mapTo(strip.scroll_area.viewport(), QtCore.QPoint()))))
        button.click()
        self.assertEqual([fake.chains["model_1"][-1]], dialog.selected_chains["model_1"])
        dialog._set_mode("object")
        self.app.processEvents()
        self.assertEqual(heights, [dialog.object_list.visualItemRect(item).height() for item in dialog.object_list.object_items()])

    def test_chain_strip_retains_full_label_width_instead_of_eliding_every_button(self):
        fake = FakeCmd()
        fake.chains["model_1"] = ["LONG_CHAIN_{:02d}".format(index) for index in range(12)]
        dialog = KYMolDialog(KYMolController(fake, reporter=lambda message: None))
        self.addCleanup(dialog.close)
        dialog.resize(540, 400)
        dialog.show()
        self.app.processEvents()
        for chain in fake.chains["model_1"]:
            button = dialog._chain_buttons[("model_1", chain)]
            required_width = button.fontMetrics().horizontalAdvance(chain) + 10
            if not button.icon().isNull():
                required_width += button.iconSize().width() + 4
            self.assertGreaterEqual(button.width(), required_width)
        strip = dialog.object_list.itemWidget(dialog.object_list.item(0), 1)
        self.assertGreater(strip.content.width(), strip.scroll_area.viewport().width())
        self.assertTrue(strip.next_button.isEnabled())

    def test_pending_long_chain_labels_survive_widget_polish_and_mode_rebuild(self):
        fake = FakeCmd()
        fake.groups = {"first_group": ["model_1", "model_2"]}
        fake.chains["model_3"] = ["LONG_CHAIN_{:02d}".format(index) for index in range(12)]
        dialog = KYMolDialog(KYMolController(fake, reporter=lambda message: None))
        self.addCleanup(dialog.close)
        dialog.chain_visual_timer.stop()
        dialog.show()
        for rebuild in (False, True):
            if rebuild:
                dialog._set_mode("object")
                dialog._set_mode("chain")
            self.app.processEvents()
            for chain in fake.chains["model_3"]:
                button = dialog._chain_buttons[("model_3", chain)]
                self.assertFalse(button.property("chainVisualKnown"))
                button.style().unpolish(button)
                button.style().polish(button)
                self.app.processEvents()
                self.assertGreaterEqual(button.width(), button.fontMetrics().horizontalAdvance(chain) + 28)

    def test_last_clicked_selected_object_is_the_gold_active_target(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        self.app.processEvents()

        first = dialog.object_list.item(0)
        second = dialog.object_list.item(1)
        QtTest.QTest.mouseClick(
            dialog.object_list.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
            dialog.object_list.visualItemRect(first).center(),
        )
        QtTest.QTest.mouseClick(
            dialog.object_list.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
            dialog.object_list.visualItemRect(second).center(),
        )
        self.app.processEvents()

        self.assertEqual(dialog.controller.state.selected, ["model_1", "model_2"])
        self.assertEqual(dialog.controller.state.active, "model_2")
        self.assertEqual(second.background(0).color().name(), GOLD)
        self.assertNotEqual(first.background(0).color().name(), GOLD)
        second_rect = dialog.object_list.visualItemRect(second)
        rendered = dialog.object_list.viewport().grab().toImage()
        # Sample empty cell background, not the first glyph's antialiased edge.
        sample_x = dialog.object_list.columnWidth(0) - 20
        rendered_gold = rendered.pixelColor(sample_x, second_rect.center().y())
        expected_gold = QtGui.QColor(GOLD)
        color_distance = sum(
            abs(actual - expected)
            for actual, expected in zip(rendered_gold.getRgb()[:3], expected_gold.getRgb()[:3])
        )
        self.assertLess(color_distance, 50)
        dialog.close()

    def test_clicking_blank_tree_space_clears_selection_and_active_target(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        first = dialog.object_list.item(0)
        second = dialog.object_list.item(1)
        first.setSelected(True)
        second.setSelected(True)
        dialog.object_list.setCurrentItem(second)
        self.app.processEvents()

        last_rect = dialog.object_list.visualItemRect(dialog.object_list.item(2))
        blank_position = QtCore.QPoint(10, last_rect.bottom() + 20)
        self.assertIsNone(dialog.object_list.itemAt(blank_position))
        QtTest.QTest.mouseClick(
            dialog.object_list.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            blank_position,
        )
        self.app.processEvents()

        self.assertEqual([], dialog.controller.state.selected)
        self.assertIsNone(dialog.controller.state.active)
        dialog.close()

    def test_plain_ctrl_and_shift_clicks_follow_blender_selection_rules(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        self.app.processEvents()
        first, second, third = [dialog.object_list.item(index) for index in range(3)]

        def click(item, modifiers=QtCore.Qt.NoModifier):
            QtTest.QTest.mouseClick(
                dialog.object_list.viewport(),
                QtCore.Qt.LeftButton,
                modifiers,
                dialog.object_list.visualItemRect(item).center(),
            )
            self.app.processEvents()

        click(first)
        self.assertEqual(["model_1"], dialog.controller.state.selected)
        self.assertEqual("model_1", dialog.controller.state.active)

        click(second, QtCore.Qt.ControlModifier)
        self.assertEqual(["model_1", "model_2"], dialog.controller.state.selected)
        self.assertEqual("model_2", dialog.controller.state.active)

        click(second, QtCore.Qt.ControlModifier)
        self.assertEqual(["model_1"], dialog.controller.state.selected)
        self.assertEqual("model_1", dialog.controller.state.active)

        click(third, QtCore.Qt.ShiftModifier)
        self.assertEqual(
            ["model_1", "model_2", "model_3"], dialog.controller.state.selected
        )
        self.assertEqual("model_3", dialog.controller.state.active)

        click(second)
        self.assertEqual(["model_2"], dialog.controller.state.selected)
        self.assertEqual("model_2", dialog.controller.state.active)
        dialog.close()

    def test_x_and_delete_keys_confirm_and_remove_panel_selected_objects(self):
        for key in (QtCore.Qt.Key_X, QtCore.Qt.Key_Delete):
            with self.subTest(key=key):
                fake_cmd = FakeCmd()
                dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
                dialog.show()
                first = dialog.object_list.item(0)
                second = dialog.object_list.item(1)
                dialog.object_list.setCurrentItem(second)
                first.setSelected(True)
                second.setSelected(True)
                dialog.object_list.setFocus()
                self.app.processEvents()

                with patch.object(
                    QtWidgets.QMessageBox,
                    "question",
                    return_value=QtWidgets.QMessageBox.Yes,
                ):
                    QtTest.QTest.keyClick(dialog.object_list, key)
                    self.app.processEvents()

                self.assertEqual(["model_3"], fake_cmd.objects)
                self.assertEqual(1, dialog.object_list.count())
                dialog.close()
            self.app.processEvents()

    def test_h_alt_h_and_slash_control_visibility_from_the_object_list(self):
        fake_cmd = FakeCmd()
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        first = dialog.object_list.item(0)
        second = dialog.object_list.item(1)
        dialog.object_list.setCurrentItem(second)
        first.setSelected(True)
        second.setSelected(True)
        dialog.object_list.setFocus()
        self.app.processEvents()

        QtTest.QTest.keyClick(dialog.object_list, QtCore.Qt.Key_H)
        self.app.processEvents()
        self.assertCountEqual(
            [("disable", "model_1"), ("disable", "model_2")],
            fake_cmd.calls,
        )

        fake_cmd.calls.clear()
        QtTest.QTest.keyClick(dialog.object_list, QtCore.Qt.Key_H)
        self.app.processEvents()
        self.assertCountEqual(
            [("enable", "model_1"), ("enable", "model_2")],
            fake_cmd.calls,
        )

        fake_cmd.calls.clear()
        QtTest.QTest.keyClick(
            dialog.object_list,
            QtCore.Qt.Key_H,
            QtCore.Qt.AltModifier,
        )
        self.app.processEvents()
        self.assertEqual(
            [("enable", "model_1"), ("enable", "model_2"), ("enable", "model_3")],
            fake_cmd.calls,
        )

        fake_cmd.calls.clear()
        QtTest.QTest.keyClick(dialog.object_list, QtCore.Qt.Key_Slash)
        self.app.processEvents()
        self.assertEqual(("disable", "all"), fake_cmd.calls[0])
        self.assertCountEqual(
            [("enable", "model_1"), ("enable", "model_2")],
            fake_cmd.calls[1:],
        )
        dialog.close()

    def test_home_hides_rename_delete_buttons_and_f_focuses_active(self):
        fake_cmd = FakeCmd()
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        second = dialog.object_list.item(1)
        dialog.object_list.select_exclusive(second)
        dialog.object_list.setFocus()
        self.app.processEvents()

        button_texts = {
            button.text() for button in dialog.findChildren(QtWidgets.QPushButton)
        }
        self.assertNotIn("Rename active (F2)", button_texts)
        self.assertNotIn("Delete selected (X / Del)", button_texts)
        self.assertIn("Toggle selected visibility (H)", button_texts)

        QtTest.QTest.keyClick(dialog.object_list, QtCore.Qt.Key_F)
        self.app.processEvents()
        self.assertEqual(("orient", "model_2"), fake_cmd.calls[-1])
        dialog.close()

    def test_right_click_object_menu_can_rename_the_clicked_object(self):
        fake_cmd = FakeCmd()
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        first = dialog.object_list.item(0)
        position = dialog.object_list.visualItemRect(first).center()
        self.app.processEvents()

        def choose_rename(menu, global_position):
            return next(action for action in menu.actions() if action.text().startswith("Rename"))

        with patch.object(QtWidgets.QMenu, "exec_", new=choose_rename):
            with patch.object(
                QtWidgets.QInputDialog,
                "getText",
                return_value=("renamed_from_menu", True),
            ):
                dialog._show_object_context_menu(position)
                self.app.processEvents()

        self.assertIn("renamed_from_menu", fake_cmd.objects)
        self.assertEqual("renamed_from_menu", dialog.controller.state.active)
        dialog.close()

    def test_panel_can_be_narrowed_and_has_windows_minimize_controls(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        self.app.processEvents()
        self.assertEqual("KyMol — Structure Review", dialog.windowTitle())
        original_width = dialog.width()

        dialog.resize(540, 460)
        self.app.processEvents()

        self.assertLess(dialog.width(), original_width)
        self.assertLessEqual(dialog.width(), 560)
        self.assertLessEqual(dialog.height(), 480)
        self.assertTrue(dialog.isSizeGripEnabled())
        self.assertTrue(dialog.windowFlags() & QtCore.Qt.WindowMinimizeButtonHint)
        self.assertFalse(dialog.windowFlags() & QtCore.Qt.WindowContextHelpButtonHint)
        dialog.close()

    def test_many_status_lines_do_not_shrink_the_chain_list(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.resize(820, 620)
        dialog.show()
        dialog._set_mode("chain")
        self.app.processEvents()
        initial_list_height = dialog.object_list.height()
        initial_status_height = dialog.status.height()

        dialog._set_status(
            "\n".join("Operation {} completed".format(index) for index in range(50))
        )
        self.app.processEvents()

        self.assertEqual(initial_status_height, dialog.status.height())
        self.assertEqual(initial_list_height, dialog.object_list.height())
        self.assertGreaterEqual(dialog.object_list.height(), 160)
        dialog.close()

    def test_pin_button_toggles_always_on_top_without_closing_the_panel(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        self.app.processEvents()
        self.assertFalse(dialog.is_pinned)
        self.assertFalse(dialog.windowFlags() & QtCore.Qt.WindowStaysOnTopHint)

        QtTest.QTest.mouseClick(dialog.pin_button, QtCore.Qt.LeftButton)
        self.app.processEvents()
        self.assertTrue(dialog.is_pinned)
        self.assertTrue(dialog.windowFlags() & QtCore.Qt.WindowStaysOnTopHint)
        self.assertTrue(dialog.isVisible())

        QtTest.QTest.mouseClick(dialog.pin_button, QtCore.Qt.LeftButton)
        self.app.processEvents()
        self.assertFalse(dialog.is_pinned)
        self.assertFalse(dialog.windowFlags() & QtCore.Qt.WindowStaysOnTopHint)
        self.assertTrue(dialog.isVisible())
        dialog.close()

    def test_tab_hotbox_switches_to_chain_mode_and_shows_chain_tiles(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        dialog.object_list.setFocus()
        self.app.processEvents()

        self.assertEqual("chain", dialog.mode)
        self.assertFalse(dialog.object_list.isColumnHidden(1))
        dialog.chain_mode_toggle.setChecked(False)
        self.assertEqual("object", dialog.mode)
        self.assertTrue(dialog.object_list.isColumnHidden(1))

        QtTest.QTest.keyClick(dialog.object_list, QtCore.Qt.Key_Tab)
        self.app.processEvents()
        self.assertTrue(dialog.mode_hotbox.isVisible())

        QtTest.QTest.mouseClick(
            dialog.mode_hotbox.chain_mode_button, QtCore.Qt.LeftButton
        )
        self.app.processEvents()

        self.assertEqual("chain", dialog.mode)
        self.assertFalse(dialog.object_list.isColumnHidden(1))
        first = dialog.object_list.item(0)
        chain_widget = dialog.object_list.itemWidget(first, 1)
        self.assertIsNotNone(chain_widget)
        self.assertEqual(
            ["A", "B"],
            [button.text() for button in chain_widget.findChildren(QtWidgets.QToolButton) if button.isCheckable()],
        )
        dialog.close()

    def test_chain_tiles_match_pymol_colors_and_mark_hidden_chains(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        dialog._set_mode("chain")
        self.app.processEvents()
        first = dialog.object_list.item(0)
        chain_widget = dialog.object_list.itemWidget(first, 1)
        buttons = {
            button.text(): button
            for button in chain_widget.findChildren(QtWidgets.QToolButton)
        }

        self.assertEqual("#00ff00", buttons["A"].property("chainColor"))
        self.assertFalse(buttons["A"].property("chainHidden"))
        self.assertTrue(buttons["A"].icon().isNull())
        self.assertEqual("#0000ff", buttons["B"].property("chainColor"))
        self.assertTrue(buttons["B"].property("chainHidden"))
        self.assertFalse(buttons["B"].icon().isNull())
        dialog.close()

    def test_chain_tiles_refresh_after_external_pymol_visibility_changes(self):
        fake_cmd = FakeCmd()
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        dialog._set_mode("chain")
        self.app.processEvents()
        first = dialog.object_list.item(0)
        chain_widget = dialog.object_list.itemWidget(first, 1)
        buttons = {
            button.text(): button
            for button in chain_widget.findChildren(QtWidgets.QToolButton)
        }
        original_button = buttons["B"]

        fake_cmd.atom_visuals[("model_1", "B")] = [(7, 32), (7, 32)]
        dialog._refresh_chain_visuals()

        self.assertIs(original_button, dialog._chain_buttons[("model_1", "B")])
        self.assertEqual("#ff0000", original_button.property("chainColor"))
        self.assertFalse(original_button.property("chainHidden"))
        self.assertTrue(original_button.icon().isNull())
        dialog.close()

    def test_chain_visual_polling_refreshes_only_one_object_per_tick(self):
        fake_cmd = FakeCmd()
        scanned_objects = []
        original_iterate = fake_cmd.iterate

        def recording_iterate(selection, expression, space):
            scanned_objects.append(
                tuple(
                    name
                    for name in fake_cmd.objects
                    if 'model "{}"'.format(name) in selection
                )
            )
            original_iterate(selection, expression, space)

        fake_cmd.iterate = recording_iterate
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        dialog.chain_visual_timer.stop()
        dialog._set_mode("chain")
        self.app.processEvents()

        self.assertTrue(scanned_objects)
        self.assertTrue(all(len(names) == 1 for names in scanned_objects))

        scanned_objects.clear()
        dialog._refresh_chain_visuals()
        dialog._refresh_chain_visuals()

        self.assertEqual([("model_1",), ("model_2",)], scanned_objects)
        dialog.close()

    def test_chain_visual_polling_pauses_while_pymol_has_focus(self):
        fake_cmd = FakeCmd()
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        dialog.chain_visual_timer.stop()
        dialog._set_mode("chain")
        self.app.processEvents()
        iterate_calls = 0
        original_iterate = fake_cmd.iterate

        def counting_iterate(selection, expression, space):
            nonlocal iterate_calls
            iterate_calls += 1
            original_iterate(selection, expression, space)

        fake_cmd.iterate = counting_iterate
        with patch.object(dialog, "isActiveWindow", return_value=False):
            dialog._refresh_chain_visuals()

        self.assertEqual(0, iterate_calls)
        dialog.close()

    def test_hotbox_right_and_left_keys_switch_modes(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        dialog.show_mode_hotbox()
        self.app.processEvents()

        QtTest.QTest.keyClick(dialog.mode_hotbox, QtCore.Qt.Key_Right)
        self.app.processEvents()
        self.assertEqual("chain", dialog.mode)

        dialog.show_mode_hotbox()
        QtTest.QTest.keyClick(dialog.mode_hotbox, QtCore.Qt.Key_Left)
        self.app.processEvents()
        self.assertEqual("object", dialog.mode)
        dialog.close()

    def test_chain_tiles_can_be_multi_selected_and_copied_with_a_base_name(self):
        fake_cmd = FakeCmd()
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        dialog._set_mode("chain")
        self.app.processEvents()
        first = dialog.object_list.item(0)
        chain_widget = dialog.object_list.itemWidget(first, 1)
        buttons = [button for button in chain_widget.findChildren(QtWidgets.QToolButton) if button.isCheckable()]

        QtTest.QTest.mouseClick(buttons[0], QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(buttons[1], QtCore.Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual({"model_1": ["A", "B"]}, dialog.selected_chains)

        with patch.object(
            QtWidgets.QInputDialog,
            "getText",
            return_value=("model_1_AB_variant", True),
        ):
            QtTest.QTest.mouseClick(
                dialog.copy_chains_button, QtCore.Qt.LeftButton
            )
            self.app.processEvents()

        self.assertIn("model_1_AB_variant", fake_cmd.objects)
        self.assertEqual(["A", "B"], fake_cmd.chains["model_1_AB_variant"])
        self.assertEqual(
            "model_1_AB_variant", dialog.controller.state.active
        )
        dialog.close()

    def test_ctrl_z_and_ctrl_shift_z_undo_and_redo_then_refresh_the_tree(self):
        fake_cmd = FakeCmd()
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        second = dialog.object_list.item(1)
        dialog.object_list.select_exclusive(second)
        self.app.processEvents()
        with patch.object(
            QtWidgets.QInputDialog,
            "getText",
            return_value=("renamed_model", True),
        ):
            dialog.rename_active()
        self.assertIn("renamed_model", fake_cmd.objects)

        QtTest.QTest.keyClick(
            dialog, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier
        )
        self.app.processEvents()
        self.assertIn("model_2", fake_cmd.objects)
        self.assertEqual("model_2", dialog.controller.state.active)

        QtTest.QTest.keyClick(
            dialog,
            QtCore.Qt.Key_Z,
            QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
        )
        self.app.processEvents()
        self.assertIn("renamed_model", fake_cmd.objects)
        self.assertEqual("renamed_model", dialog.controller.state.active)
        dialog.close()

    def test_m_creates_a_native_group_and_f2_renames_the_active_object(self):
        fake_cmd = FakeCmd()
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        first = dialog.object_list.item(0)
        second = dialog.object_list.item(1)
        dialog.object_list.setCurrentItem(second)
        first.setSelected(True)
        second.setSelected(True)
        dialog.object_list.setFocus()
        self.app.processEvents()

        with patch.object(
            QtWidgets.QInputDialog,
            "getText",
            return_value=("P1", True),
        ):
            QtTest.QTest.keyClick(dialog.object_list, QtCore.Qt.Key_M)
            self.app.processEvents()

        self.assertCountEqual(["model_1", "model_2"], fake_cmd.groups["P1"])
        group_item = dialog.object_list.topLevelItem(0)
        self.assertEqual("P1", group_item.text(0))

        dialog.object_list.setCurrentItem(group_item.child(1))
        group_item.child(1).setSelected(True)
        self.app.processEvents()
        with patch.object(
            QtWidgets.QInputDialog,
            "getText",
            return_value=("renamed_model", True),
        ):
            QtTest.QTest.keyClick(dialog.object_list, QtCore.Qt.Key_F2)
            self.app.processEvents()

        self.assertIn("renamed_model", fake_cmd.objects)
        self.assertIn("renamed_model", fake_cmd.groups["P1"])
        dialog.close()

    def test_plain_click_selects_and_drop_moves_an_object_into_a_group(self):
        fake_cmd = FakeCmd()
        fake_cmd.groups["P1"] = ["model_1"]
        dialog = KYMolDialog(KYMolController(fake_cmd, reporter=lambda message: None))
        dialog.show()
        self.app.processEvents()

        ungrouped = next(
            item
            for item in dialog.object_list.object_items()
            if item.data(0, QtCore.Qt.UserRole) == "model_3"
        )
        QtTest.QTest.mouseClick(
            dialog.object_list.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            dialog.object_list.visualItemRect(ungrouped).center(),
        )
        self.app.processEvents()
        self.assertEqual(["model_3"], dialog.controller.state.selected)

        dialog.object_list.objectsDropped.emit(["model_3"], "P1")
        self.app.processEvents()
        self.assertCountEqual(["model_1", "model_3"], fake_cmd.groups["P1"])
        dialog.close()


if __name__ == "__main__":
    unittest.main()
