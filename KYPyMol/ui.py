"""PyQt UI.  All domain operations remain in :mod:`KYPyMol.core`."""

from __future__ import annotations

import os

from pymol.Qt import QtCore, QtGui, QtWidgets

from .core import KYPyMolError


class ActiveObjectDelegate(QtWidgets.QStyledItemDelegate):
    """Keep the active target gold even when it is also a selected row."""

    def paint(self, painter, option, index):
        if index.data(QtCore.Qt.UserRole + 1):
            option = QtWidgets.QStyleOptionViewItem(option)
            option.palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#c99b12"))
            option.palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#1d1d1d"))
        super().paint(painter, option, index)


class KYPyMolDialog(QtWidgets.QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("KYPyMol — Active Object Review")
        self.setMinimumSize(570, 440)
        self._build_ui()
        self._install_shortcuts()
        self.refresh_objects()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "Multi-select objects; the last clicked item is the <b>gold active target</b>. "
            "Sync reads PyMOL <code>sele</code>, then choose its target here."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.object_list = QtWidgets.QListWidget()
        self.object_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.object_list.setItemDelegate(ActiveObjectDelegate(self.object_list))
        self.object_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.object_list.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.object_list, 1)

        line = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh objects")
        self.sync_button = QtWidgets.QPushButton("Sync PyMOL selection")
        self.refresh_button.clicked.connect(lambda: self.refresh_objects(keep_selection=True))
        self.sync_button.clicked.connect(self.sync_from_pymol)
        line.addWidget(self.refresh_button)
        line.addWidget(self.sync_button)
        line.addStretch(1)
        line.addWidget(QtWidgets.QLabel("Shared chain (optional):"))
        self.chain_edit = QtWidgets.QLineEdit()
        self.chain_edit.setPlaceholderText("e.g. A")
        self.chain_edit.setMaximumWidth(100)
        line.addWidget(self.chain_edit)
        layout.addLayout(line)

        align_line = QtWidgets.QHBoxLayout()
        self.method_combo = QtWidgets.QComboBox()
        self.method_combo.addItems(["super", "align", "cealign"])
        self.scope_combo = QtWidgets.QComboBox()
        self.scope_combo.addItem("Auto: current selection → common chain → whole object", "auto")
        self.scope_combo.addItem("Current PyMOL selection only", "selection")
        self.scope_combo.addItem("Common chain only", "common_chain")
        self.scope_combo.addItem("Whole object (protein CA)", "whole_object")
        self.align_button = QtWidgets.QPushButton("Align selected to active")
        self.align_button.setToolTip("Shift+Alt+A while this panel has focus; global fallback: Alt+A")
        self.align_button.clicked.connect(self.align)
        self.color_button = QtWidgets.QPushButton("Color chains (Alt+C)")
        self.color_button.clicked.connect(self.color_chains)
        align_line.addWidget(QtWidgets.QLabel("Method:"))
        align_line.addWidget(self.method_combo)
        align_line.addWidget(self.scope_combo, 1)
        align_line.addWidget(self.align_button)
        align_line.addWidget(self.color_button)
        layout.addLayout(align_line)

        export_line = QtWidgets.QHBoxLayout()
        self.export_mode = QtWidgets.QComboBox()
        self.export_mode.addItem("Current selection (or active object if empty)", False)
        self.export_mode.addItem("Entire active object / selected chain", True)
        self.export_pdb = QtWidgets.QPushButton("Export PDB")
        self.export_cif = QtWidgets.QPushButton("Export CIF")
        self.copy_fasta = QtWidgets.QPushButton("Copy FASTA")
        self.export_pdb.clicked.connect(lambda: self.export("pdb"))
        self.export_cif.clicked.connect(lambda: self.export("cif"))
        self.copy_fasta.clicked.connect(self.copy_fasta)
        export_line.addWidget(self.export_mode, 1)
        export_line.addWidget(self.export_pdb)
        export_line.addWidget(self.export_cif)
        export_line.addWidget(self.copy_fasta)
        layout.addLayout(export_line)

        self.status = QtWidgets.QLabel("KYPyMol is ready.")
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

    def _selected_names(self):
        return [item.data(QtCore.Qt.UserRole) for item in self.object_list.selectedItems()]

    def _current_name(self):
        item = self.object_list.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None

    def _apply_active_style(self):
        active = self.controller.state.active
        for row in range(self.object_list.count()):
            item = self.object_list.item(row)
            is_active = item.data(QtCore.Qt.UserRole) == active
            item.setData(QtCore.Qt.UserRole + 1, is_active)
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
        except KYPyMolError as exc:
            self._set_status(str(exc), error=True)
        except Exception as exc:
            self._set_status("Unexpected error: {}".format(exc), error=True)

    def refresh_objects(self, keep_selection=False):
        selected = self.controller.state.selected if keep_selection else []
        active = self.controller.state.active if keep_selection else None
        self.object_list.blockSignals(True)
        self.object_list.clear()
        for name in self.controller.molecular_objects():
            item = QtWidgets.QListWidgetItem(name)
            item.setData(QtCore.Qt.UserRole, name)
            self.object_list.addItem(item)
            if name in selected:
                item.setSelected(True)
            if name == active:
                self.object_list.setCurrentItem(item)
        self.object_list.blockSignals(False)
        self._on_selection_changed()
        self._apply_active_style()

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
        if current and current.isSelected():
            self.controller.set_active(current.data(QtCore.Qt.UserRole))
            self._apply_active_style()
            self._set_status(self.controller.status_text())

    def align(self):
        self._run(lambda: self.controller.align_selected(
            method=self.method_combo.currentText(),
            scope=self.scope_combo.currentData(),
            chain=self.chain_edit.text(),
        ))

    def color_chains(self):
        self._run(self.controller.color_selected_by_chain)

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
            QtWidgets.QApplication.clipboard().setText(fasta)
            self._set_status("Copied FASTA to clipboard. " + self.controller.status_text())
        self._run(action)
