"""PyQt UI. All domain operations remain in :mod:`KYMol.core`."""

from __future__ import annotations

import json
import os

from pymol.Qt import QtCore, QtGui, QtWidgets

from .core import KYMolError


ACTIVE_GOLD = QtGui.QColor("#c99b12")
ACTIVE_TEXT = QtGui.QColor("#1d1d1d")
ITEM_KIND_ROLE = QtCore.Qt.UserRole + 2
OBJECT_KIND = "object"
GROUP_KIND = "group"


class ObjectGroupTree(QtWidgets.QTreeWidget):
    """Tree where Ctrl/Shift selects and an unmodified mouse drag moves objects."""

    objectsDropped = QtCore.Signal(list, str)
    MIME_TYPE = "application/x-kymol-object-names"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self._drag_start = None
        self._drag_item = None
        self._delegated_press = False

    def object_items(self):
        items = []
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if item.data(0, ITEM_KIND_ROLE) == OBJECT_KIND:
                items.append(item)
            iterator += 1
        return items

    # Compatibility helpers used by tests and by the former flat-list code.
    def count(self):
        return len(self.object_items())

    def item(self, row):
        items = self.object_items()
        return items[row] if 0 <= row < len(items) else None

    def mousePressEvent(self, event):
        modifiers = event.modifiers()
        self._delegated_press = bool(
            modifiers & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier)
        )
        if self._delegated_press:
            self._drag_start = None
            self._drag_item = None
            super().mousePressEvent(event)
            return
        self._drag_start = event.pos()
        self._drag_item = self.itemAt(event.pos())
        if self._drag_item is not None:
            self.setCurrentItem(
                self._drag_item,
                0,
                QtCore.QItemSelectionModel.NoUpdate,
            )
        event.accept()

    def mouseMoveEvent(self, event):
        if (
            self._drag_start is None
            or self._drag_item is None
            or not (event.buttons() & QtCore.Qt.LeftButton)
            or self._drag_item.data(0, ITEM_KIND_ROLE) != OBJECT_KIND
        ):
            return
        if (event.pos() - self._drag_start).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return
        if self._drag_item.isSelected():
            names = [
                item.data(0, QtCore.Qt.UserRole)
                for item in self.selectedItems()
                if item.data(0, ITEM_KIND_ROLE) == OBJECT_KIND
            ]
        else:
            names = [self._drag_item.data(0, QtCore.Qt.UserRole)]
        mime = QtCore.QMimeData()
        mime.setData(self.MIME_TYPE, json.dumps(names).encode("utf-8"))
        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(QtCore.Qt.MoveAction)
        self._drag_start = None
        self._drag_item = None

    def mouseReleaseEvent(self, event):
        if self._delegated_press:
            super().mouseReleaseEvent(event)
        else:
            if (
                self._drag_item is not None
                and self._drag_item.data(0, ITEM_KIND_ROLE) == GROUP_KIND
            ):
                self._drag_item.setExpanded(not self._drag_item.isExpanded())
            event.accept()
        self._drag_start = None
        self._drag_item = None
        self._delegated_press = False

    def _drop_group(self, position):
        item = self.itemAt(position)
        if item is not None and item.data(0, ITEM_KIND_ROLE) == OBJECT_KIND:
            item = item.parent()
        if item is not None and item.data(0, ITEM_KIND_ROLE) == GROUP_KIND:
            return item.data(0, QtCore.Qt.UserRole)
        return None

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE) and self._drop_group(event.pos()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        group_name = self._drop_group(event.pos())
        if not group_name or not event.mimeData().hasFormat(self.MIME_TYPE):
            event.ignore()
            return
        names = json.loads(bytes(event.mimeData().data(self.MIME_TYPE)).decode("utf-8"))
        self.objectsDropped.emit(names, group_name)
        event.acceptProposedAction()


class ActiveObjectDelegate(QtWidgets.QStyledItemDelegate):
    """Keep the active target gold even when it is also a selected row."""

    def paint(self, painter, option, index):
        if index.data(QtCore.Qt.UserRole + 1):
            option = QtWidgets.QStyleOptionViewItem(option)
            option.backgroundBrush = QtGui.QBrush(ACTIVE_GOLD)
            option.palette.setColor(QtGui.QPalette.Base, ACTIVE_GOLD)
            option.palette.setColor(QtGui.QPalette.Highlight, ACTIVE_GOLD)
            option.palette.setColor(QtGui.QPalette.Text, ACTIVE_TEXT)
            option.palette.setColor(QtGui.QPalette.HighlightedText, ACTIVE_TEXT)
        super().paint(painter, option, index)


class KYMolDialog(QtWidgets.QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("KYMol — Structure Review")
        flags = self.windowFlags()
        flags |= QtCore.Qt.WindowMinimizeButtonHint
        flags &= ~QtCore.Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(500, 400)
        self.resize(820, 620)
        self._build_ui()
        self._install_shortcuts()
        self.refresh_objects()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "Use <b>Ctrl/Shift</b> to select objects; the last selected row is the "
            "<b>gold active target</b>. Press M to create a folder. Plain mouse drag moves "
            "objects into folders without changing the selection."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.object_list = ObjectGroupTree()
        self.object_list.setItemDelegate(ActiveObjectDelegate(self.object_list))
        self.object_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.object_list.currentItemChanged.connect(self._on_current_item_changed)
        self.object_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.object_list.objectsDropped.connect(self._move_objects_to_group)
        layout.addWidget(self.object_list, 1)

        object_actions = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh objects")
        self.sync_button = QtWidgets.QPushButton("Import PyMOL selection (optional)")
        self.refresh_button.clicked.connect(lambda: self.refresh_objects(keep_selection=True))
        self.sync_button.clicked.connect(self.sync_from_pymol)
        object_actions.addWidget(self.refresh_button)
        object_actions.addWidget(self.sync_button)
        object_actions.addStretch(1)
        layout.addLayout(object_actions)

        object_edit_actions = QtWidgets.QHBoxLayout()
        self.create_group_button = QtWidgets.QPushButton("Create group (M)")
        self.rename_button = QtWidgets.QPushButton("Rename active (F2)")
        self.create_group_button.clicked.connect(self.create_group)
        self.rename_button.clicked.connect(self.rename_active)
        object_edit_actions.addWidget(self.create_group_button)
        object_edit_actions.addWidget(self.rename_button)
        object_edit_actions.addStretch(1)
        layout.addLayout(object_edit_actions)

        chain_line = QtWidgets.QHBoxLayout()
        chain_line.addWidget(QtWidgets.QLabel("Shared chain (optional):"))
        self.chain_edit = QtWidgets.QLineEdit()
        self.chain_edit.setPlaceholderText("e.g. A")
        self.chain_edit.setMaximumWidth(100)
        chain_line.addWidget(self.chain_edit)
        chain_line.addStretch(1)
        layout.addLayout(chain_line)

        align_settings = QtWidgets.QHBoxLayout()
        self.method_combo = QtWidgets.QComboBox()
        self.method_combo.addItems(["super", "align", "cealign"])
        self.scope_combo = QtWidgets.QComboBox()
        self.scope_combo.addItem("Auto: common chain, then whole object", "auto")
        self.scope_combo.addItem("Current PyMOL selection only", "selection")
        self.scope_combo.addItem("Common chain only", "common_chain")
        self.scope_combo.addItem("Whole object (protein CA)", "whole_object")
        self.align_button = QtWidgets.QPushButton("Align selected to active")
        self.align_button.setToolTip("Shift+Alt+A while this panel has focus; global fallback: Alt+A")
        self.align_button.clicked.connect(self.align)
        self.color_button = QtWidgets.QPushButton("Color chains (Alt+C)")
        self.color_button.clicked.connect(self.color_chains)
        align_settings.addWidget(QtWidgets.QLabel("Method:"))
        align_settings.addWidget(self.method_combo)
        align_settings.addWidget(self.scope_combo, 1)
        layout.addLayout(align_settings)

        align_actions = QtWidgets.QHBoxLayout()
        align_actions.addWidget(self.align_button)
        align_actions.addWidget(self.color_button)
        align_actions.addStretch(1)
        layout.addLayout(align_actions)

        display_grid = QtWidgets.QGridLayout()
        self.show_button = QtWidgets.QPushButton("Show selected")
        self.hide_button = QtWidgets.QPushButton("Hide selected (H)")
        self.only_button = QtWidgets.QPushButton("Only selected (/)")
        self.show_all_button = QtWidgets.QPushButton("Show all (Alt+H)")
        self.focus_button = QtWidgets.QPushButton("Focus active")
        self.delete_button = QtWidgets.QPushButton("Delete selected (X / Del)")
        self.delete_button.setStyleSheet(
            "QPushButton { color: #ffdddd; background: #7f1d1d; padding: 4px 8px; }"
        )
        self.show_button.clicked.connect(lambda: self.display_selected("show"))
        self.hide_button.clicked.connect(lambda: self.display_selected("hide"))
        self.only_button.clicked.connect(lambda: self.display_selected("only"))
        self.show_all_button.clicked.connect(self.show_all_objects)
        self.focus_button.clicked.connect(self.focus_active)
        self.delete_button.clicked.connect(self.delete_selected)
        display_grid.addWidget(self.show_button, 0, 0)
        display_grid.addWidget(self.hide_button, 0, 1)
        display_grid.addWidget(self.only_button, 0, 2)
        display_grid.addWidget(self.focus_button, 1, 0)
        display_grid.addWidget(self.show_all_button, 1, 1)
        display_grid.addWidget(self.delete_button, 1, 2)
        layout.addLayout(display_grid)

        export_mode_line = QtWidgets.QHBoxLayout()
        self.export_mode = QtWidgets.QComboBox()
        self.export_mode.addItem("Active object / chain field", True)
        self.export_mode.addItem("PyMOL atom selection within active (optional)", False)
        export_mode_line.addWidget(self.export_mode, 1)
        layout.addLayout(export_mode_line)

        export_actions = QtWidgets.QHBoxLayout()
        self.export_pdb = QtWidgets.QPushButton("Export PDB")
        self.export_cif = QtWidgets.QPushButton("Export CIF")
        self.copy_fasta_button = QtWidgets.QPushButton("Show / Copy FASTA")
        self.export_pdb.clicked.connect(lambda: self.export("pdb"))
        self.export_cif.clicked.connect(lambda: self.export("cif"))
        self.copy_fasta_button.clicked.connect(self.copy_fasta)
        export_actions.addWidget(self.export_pdb)
        export_actions.addWidget(self.export_cif)
        export_actions.addWidget(self.copy_fasta_button)
        export_actions.addStretch(1)
        layout.addLayout(export_actions)

        self.sequence_preview = QtWidgets.QPlainTextEdit()
        self.sequence_preview.setReadOnly(True)
        self.sequence_preview.setPlaceholderText(
            "The active object's FASTA sequence will appear here and be copied to the clipboard."
        )
        self.sequence_preview.setMaximumHeight(110)
        layout.addWidget(self.sequence_preview)

        self.status = QtWidgets.QLabel("KYMol is ready.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("QLabel { padding: 7px; background: #20242a; color: #e8edf2; border-radius: 3px; }")
        layout.addWidget(self.status)

    def _install_shortcuts(self):
        # Qt can receive this non-PyMOL documented combination while the app runs.
        # PyMOL's documented global fallback is registered as ALT-A in __init__.py.
        self.align_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Shift+Alt+A"), self)
        self.align_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.align_shortcut.activated.connect(self.align)
        self.color_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Alt+C"), self)
        self.color_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.color_shortcut.activated.connect(self.color_chains)
        self.delete_x_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("X"), self.object_list)
        self.delete_x_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.delete_x_shortcut.activated.connect(self.delete_selected)
        self.delete_key_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), self.object_list)
        self.delete_key_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.delete_key_shortcut.activated.connect(self.delete_selected)
        self.hide_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("H"), self.object_list)
        self.hide_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.hide_shortcut.activated.connect(lambda: self.display_selected("hide"))
        self.show_all_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Alt+H"), self)
        self.show_all_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.show_all_shortcut.activated.connect(self.show_all_objects)
        self.only_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("/"), self.object_list)
        self.only_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.only_shortcut.activated.connect(lambda: self.display_selected("only"))
        self.group_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("M"), self.object_list)
        self.group_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.group_shortcut.activated.connect(self.create_group)
        self.rename_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("F2"), self.object_list)
        self.rename_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.rename_shortcut.activated.connect(self.rename_active)

    def _selected_names(self):
        return [
            item.data(0, QtCore.Qt.UserRole)
            for item in self.object_list.selectedItems()
            if item.data(0, ITEM_KIND_ROLE) == OBJECT_KIND
        ]

    def _current_name(self):
        item = self.object_list.currentItem()
        if item and item.data(0, ITEM_KIND_ROLE) == OBJECT_KIND:
            return item.data(0, QtCore.Qt.UserRole)
        return None

    def _current_group(self):
        item = self.object_list.currentItem()
        if item and item.data(0, ITEM_KIND_ROLE) == GROUP_KIND:
            return item.data(0, QtCore.Qt.UserRole)
        return None

    def _apply_active_style(self):
        active = self.controller.state.active
        for item in self.object_list.object_items():
            is_active = item.data(0, QtCore.Qt.UserRole) == active
            item.setData(0, QtCore.Qt.UserRole + 1, is_active)
            item.setBackground(0, QtGui.QBrush(ACTIVE_GOLD) if is_active else QtGui.QBrush())
            item.setForeground(0, QtGui.QBrush(ACTIVE_TEXT) if is_active else QtGui.QBrush())
        self.object_list.viewport().update()

    def _set_status(self, message, error=False):
        self.status.setText(message)
        color = "#7f1d1d" if error else "#20242a"
        self.status.setStyleSheet("QLabel { padding: 7px; background: %s; color: #e8edf2; border-radius: 3px; }" % color)

    def _run(self, operation):
        try:
            value = operation()
            self._set_status(self.controller.status_text())
            return value
        except KYMolError as exc:
            self._set_status(str(exc), error=True)
        except Exception as exc:
            self._set_status("Unexpected error: {}".format(exc), error=True)

    def refresh_objects(self, keep_selection=False):
        selected = self.controller.state.selected if keep_selection else []
        active = self.controller.state.active if keep_selection else None
        self.object_list.blockSignals(True)
        self.object_list.clear()
        objects = self.controller.molecular_objects()
        grouped = set()
        folder_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
        for group_name in self.controller.group_names():
            group_item = QtWidgets.QTreeWidgetItem([group_name])
            group_item.setData(0, QtCore.Qt.UserRole, group_name)
            group_item.setData(0, ITEM_KIND_ROLE, GROUP_KIND)
            group_item.setIcon(0, folder_icon)
            group_item.setFlags(
                QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsDropEnabled
            )
            self.object_list.addTopLevelItem(group_item)
            for name in self.controller.group_members(group_name):
                if name not in objects or name in grouped:
                    continue
                grouped.add(name)
                item = self._new_object_item(name)
                group_item.addChild(item)
                self._restore_item_state(item, name, selected, active)
            group_item.setExpanded(True)
        for name in objects:
            if name in grouped:
                continue
            item = self._new_object_item(name)
            self.object_list.addTopLevelItem(item)
            self._restore_item_state(item, name, selected, active)
        self.object_list.blockSignals(False)
        self._on_selection_changed()
        self._apply_active_style()

    def _new_object_item(self, name):
        item = QtWidgets.QTreeWidgetItem([name])
        item.setData(0, QtCore.Qt.UserRole, name)
        item.setData(0, ITEM_KIND_ROLE, OBJECT_KIND)
        item.setFlags(
            QtCore.Qt.ItemIsEnabled
            | QtCore.Qt.ItemIsSelectable
            | QtCore.Qt.ItemIsDragEnabled
        )
        return item

    def _restore_item_state(self, item, name, selected, active):
        if name in selected:
            item.setSelected(True)
        if name == active:
            self.object_list.setCurrentItem(item)

    def sync_from_pymol(self):
        def action():
            self.controller.sync_from_pymol_selection()
            self.refresh_objects(keep_selection=True)
        self._run(action)

    def _on_selection_changed(self):
        names = self._selected_names()
        active = self._current_name()
        if active not in names:
            active = self.controller.state.active if self.controller.state.active in names else (names[-1] if names else None)
        self.controller.set_selection(names, active)
        self._apply_active_style()
        self._set_status(self.controller.status_text())

    def _on_current_item_changed(self, current, previous):
        if (
            current
            and current.data(0, ITEM_KIND_ROLE) == OBJECT_KIND
            and current.isSelected()
        ):
            self.controller.set_active(current.data(0, QtCore.Qt.UserRole))
            self._apply_active_style()
            self._set_status(self.controller.status_text())

    def _on_item_double_clicked(self, item, column):
        if item.data(0, ITEM_KIND_ROLE) != GROUP_KIND:
            return
        group_name = item.data(0, QtCore.Qt.UserRole)

        def action():
            self.controller.select_group(group_name)
            self.refresh_objects(keep_selection=True)

        self._run(action)

    def align(self):
        self._run(lambda: self.controller.align_selected(
            method=self.method_combo.currentText(),
            scope=self.scope_combo.currentData(),
            chain=self.chain_edit.text(),
        ))

    def color_chains(self):
        self._run(self.controller.color_selected_by_chain)

    def display_selected(self, mode):
        group_name = self._current_group()
        if group_name:
            self._run(lambda: self.controller.display_group(group_name, mode))
        else:
            self._run(lambda: self.controller.display_selected(mode))

    def show_all_objects(self):
        self._run(self.controller.show_all_objects)

    def focus_active(self):
        self._run(self.controller.focus_active)

    def create_group(self):
        if not self.controller.state.selected:
            self._set_status("Select objects with Ctrl/Shift before creating a group.", error=True)
            return
        default_name = self.controller.next_group_name()
        group_name, accepted = QtWidgets.QInputDialog.getText(
            self,
            "Create KYMol group",
            "Group name:",
            QtWidgets.QLineEdit.Normal,
            default_name,
        )
        if not accepted:
            return

        def action():
            created = self.controller.create_group(group_name)
            self.refresh_objects(keep_selection=True)
            return created

        self._run(action)

    def rename_active(self):
        active = self.controller.state.active
        if not active:
            self._set_status("Select an active object before renaming.", error=True)
            return
        new_name, accepted = QtWidgets.QInputDialog.getText(
            self,
            "Rename active object",
            "New object name:",
            QtWidgets.QLineEdit.Normal,
            active,
        )
        if not accepted:
            return

        def action():
            renamed = self.controller.rename_active(new_name)
            self.refresh_objects(keep_selection=True)
            return renamed

        self._run(action)

    def _move_objects_to_group(self, object_names, group_name):
        def action():
            moved = self.controller.assign_objects_to_group(object_names, group_name)
            self.refresh_objects(keep_selection=True)
            return moved

        self._run(action)

    def delete_selected(self):
        names = list(self.controller.state.selected)
        if not names:
            self._set_status("Select at least one object before deleting.", error=True)
            return
        preview = "\n".join(names[:8])
        if len(names) > 8:
            preview += "\n... and {} more".format(len(names) - 8)
        answer = QtWidgets.QMessageBox.question(
            self,
            "Delete selected objects?",
            "Delete {} object(s) from the current PyMOL session?\n\n{}\n\n"
            "Reload the original files to recover them.".format(len(names), preview),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        def action():
            deleted = self.controller.delete_selected()
            self.refresh_objects()
            return deleted

        self._run(action)

    def _export_selection(self):
        return bool(self.export_mode.currentData()), self.chain_edit.text().strip()

    def export(self, file_format):
        active = self.controller.state.active or "structure"
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export {}".format(file_format.upper()), "{}.{}".format(active, file_format),
            "{} files (*.{})".format(file_format.upper(), file_format),
        )
        if not filename:
            return
        if not filename.lower().endswith("." + file_format):
            filename += "." + file_format
        whole_chain, chain = self._export_selection()
        self._run(lambda: self.controller.export_active(filename, file_format, whole_chain, chain))

    def copy_fasta(self):
        whole_chain, chain = self._export_selection()
        def action():
            fasta = self.controller.fasta_active(whole_chain, chain)
            self.sequence_preview.setPlainText(fasta)
            QtWidgets.QApplication.clipboard().setText(fasta)
            self._set_status("Copied FASTA to clipboard. " + self.controller.status_text())
        self._run(action)
