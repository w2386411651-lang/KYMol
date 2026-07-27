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
        self.calls = []
        self.groups = {}

    def get_names_of_type(self, object_type):
        if object_type == "object:group":
            return list(self.groups)
        return self.objects

    def get_names(self, kind="all", selection=""):
        if kind == "all":
            return list(self.objects) + list(self.groups)
        if kind == "objects" and selection.startswith("?"):
            return list(self.groups.get(selection[1:], []))
        return list(self.objects)

    def delete(self, object_name):
        self.objects.remove(object_name)

    def enable(self, object_name):
        self.calls.append(("enable", object_name))

    def disable(self, object_name):
        self.calls.append(("disable", object_name))

    def group(self, group_name, members="", action="auto"):
        self.groups.setdefault(group_name, [])
        for member in members.split():
            for group_members in self.groups.values():
                if member in group_members:
                    group_members.remove(member)
            self.groups[group_name].append(member)

    def set_name(self, old_name, new_name):
        self.objects[self.objects.index(old_name)] = new_name
        for group_members in self.groups.values():
            if old_name in group_members:
                group_members[group_members.index(old_name)] = new_name


class KYMolDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

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
        rendered_gold = rendered.pixelColor(second_rect.left() + 4, second_rect.center().y())
        expected_gold = QtGui.QColor(GOLD)
        color_distance = sum(
            abs(actual - expected)
            for actual, expected in zip(rendered_gold.getRgb()[:3], expected_gold.getRgb()[:3])
        )
        self.assertLess(color_distance, 50)
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

    def test_panel_can_be_narrowed_and_has_windows_minimize_controls(self):
        dialog = KYMolDialog(KYMolController(FakeCmd(), reporter=lambda message: None))
        dialog.show()
        self.app.processEvents()
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

    def test_plain_click_does_not_select_and_drop_moves_an_object_into_a_group(self):
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
        self.assertEqual([], dialog.controller.state.selected)

        QtTest.QTest.mouseClick(
            dialog.object_list.viewport(),
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier,
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
