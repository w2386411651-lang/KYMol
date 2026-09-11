"""PyQt UI. All domain operations remain in :mod:`KYMol.core`."""

from __future__ import annotations

import json
import os

from pymol.Qt import QtCore, QtGui, QtWidgets

from .core import KYMolError


ACTIVE_GOLD = QtGui.QColor("#c99b12")
ACTIVE_TEXT = QtGui.QColor("#1d1d1d")
CHAIN_SWATCHES = (
    "#6ea8fe",
    "#ff7f6e",
    "#70d6a3",
    "#d9a6ff",
    "#ffd166",
    "#62c7d9",
    "#f78fb3",
    "#a8d672",
)
ITEM_KIND_ROLE = QtCore.Qt.UserRole + 2
OBJECT_KIND = "object"
GROUP_KIND = "group"
STATUS_PANEL_HEIGHT = 56
CHAIN_VISUAL_REFRESH_INTERVAL_MS = 250
SEARCH_MATCH_ROLE = QtCore.Qt.UserRole + 3
SEARCH_CURRENT_ROLE = QtCore.Qt.UserRole + 4


def chain_swatch(chain):
    if not chain:
        return CHAIN_SWATCHES[0]
    index = sum(
        (position + 1) * ord(character)
        for position, character in enumerate(chain)
    )
    return CHAIN_SWATCHES[index % len(CHAIN_SWATCHES)]


def contrast_text_color(color_hex):
    color = QtGui.QColor(color_hex)
    luminance = (
        0.2126 * color.redF()
        + 0.7152 * color.greenF()
        + 0.0722 * color.blueF()
    )
    return "#111820" if luminance > 0.55 else "#ffffff"


def hidden_chain_icon(stroke_color="#17202a"):
    pixmap = QtGui.QPixmap(14, 14)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(stroke_color), 1.6)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    painter.setPen(pen)
    eye = QtGui.QPainterPath()
    eye.moveTo(1.0, 7.0)
    eye.cubicTo(3.5, 3.5, 10.5, 3.5, 13.0, 7.0)
    eye.cubicTo(10.5, 10.5, 3.5, 10.5, 1.0, 7.0)
    painter.drawPath(eye)
    painter.drawLine(2, 2, 12, 12)
    painter.end()
    return QtGui.QIcon(pixmap)


class ObjectGroupTree(QtWidgets.QTreeWidget):
    """Blender-like object selection plus unmodified drag-to-group behavior."""

    objectsDropped = QtCore.Signal(list, str)
    MIME_TYPE = "application/x-kymol-object-names"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderHidden(True)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.header().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Interactive
        )
        self.header().resizeSection(1, 220)
        self.setUniformRowHeights(True)
        self.setTextElideMode(QtCore.Qt.ElideMiddle)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self._drag_start = None
        self._drag_item = None
        self._press_modifiers = QtCore.Qt.NoModifier
        self._drag_performed = False
        self._selection_anchor = None

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

    def _set_current_without_selecting(self, item):
        self.setCurrentItem(item, 0, QtCore.QItemSelectionModel.NoUpdate)

    def select_exclusive(self, item):
        self.clearSelection()
        if item is not None and item.data(0, ITEM_KIND_ROLE) == OBJECT_KIND:
            item.setSelected(True)
            self._set_current_without_selecting(item)
            self._selection_anchor = item
        else:
            self.setCurrentItem(None)
            self._selection_anchor = None

    def _toggle_item(self, item):
        if item.isSelected():
            item.setSelected(False)
            remaining = [
                candidate for candidate in self.object_items() if candidate.isSelected()
            ]
            fallback = remaining[-1] if remaining else None
            self._set_current_without_selecting(fallback)
            if self._selection_anchor is item:
                self._selection_anchor = fallback
        else:
            item.setSelected(True)
            self._set_current_without_selecting(item)
            self._selection_anchor = item

    def _select_range_to(self, item):
        objects = self.object_items()
        anchor = self._selection_anchor
        if anchor not in objects:
            current = self.currentItem()
            anchor = current if current in objects else None
        if anchor is None:
            self.select_exclusive(item)
            return
        start, end = sorted((objects.index(anchor), objects.index(item)))
        for candidate in objects[start : end + 1]:
            candidate.setSelected(True)
        self._set_current_without_selecting(item)

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            super().mousePressEvent(event)
            return
        modifiers = event.modifiers()
        self._press_modifiers = modifiers
        self._drag_start = event.pos()
        self._drag_item = self.itemAt(event.pos())
        self._drag_performed = False
        if self._drag_item is None:
            if modifiers == QtCore.Qt.NoModifier:
                self.select_exclusive(None)
            event.accept()
            return
        if self._drag_item.data(0, ITEM_KIND_ROLE) != OBJECT_KIND:
            self._set_current_without_selecting(self._drag_item)
            event.accept()
            return
        if modifiers & QtCore.Qt.ControlModifier:
            self._toggle_item(self._drag_item)
            self._drag_start = None
        elif modifiers & QtCore.Qt.ShiftModifier:
            self._select_range_to(self._drag_item)
            self._drag_start = None
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
        self._drag_performed = True
        drag.exec_(QtCore.Qt.MoveAction)
        self._drag_start = None
        self._drag_item = None

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._drag_item is not None and not self._drag_performed:
            kind = self._drag_item.data(0, ITEM_KIND_ROLE)
            if kind == OBJECT_KIND and self._press_modifiers == QtCore.Qt.NoModifier:
                self.select_exclusive(self._drag_item)
            elif kind == GROUP_KIND and self._press_modifiers == QtCore.Qt.NoModifier:
                self._drag_item.setExpanded(not self._drag_item.isExpanded())
        event.accept()
        self._drag_start = None
        self._drag_item = None
        self._press_modifiers = QtCore.Qt.NoModifier
        self._drag_performed = False

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
            # Keep native selected/hover themes from replacing the target marker.
            # Selection itself stays in the model.
            option.state &= ~(QtWidgets.QStyle.State_Selected | QtWidgets.QStyle.State_MouseOver | QtWidgets.QStyle.State_HasFocus)
        super().paint(painter, option, index)
        if index.column() == 0 and index.data(SEARCH_MATCH_ROLE):
            painter.save()
            pen = QtGui.QPen(QtGui.QColor("#087eaf"), 2 if index.data(SEARCH_CURRENT_ROLE) else 1)
            pen.setStyle(QtCore.Qt.SolidLine if index.data(SEARCH_CURRENT_ROLE) else QtCore.Qt.DotLine)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
            painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(28, option.fontMetrics.height() + 10))
        return size


class ChainStrip(QtWidgets.QWidget):
    """One compact row; every chain remains reachable by arrows, wheel, or Tab."""

    def __init__(self, row_height, parent=None):
        super().__init__(parent)
        self.setFixedHeight(row_height)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(1, 0, 1, 0)
        layout.setSpacing(1)
        self.previous_button = QtWidgets.QToolButton(self)
        self.previous_button.setArrowType(QtCore.Qt.LeftArrow)
        self.previous_button.setToolTip("Scroll to earlier chains")
        self.next_button = QtWidgets.QToolButton(self)
        self.next_button.setArrowType(QtCore.Qt.RightArrow)
        self.next_button.setToolTip("Scroll to later chains")
        for button in (self.previous_button, self.next_button):
            button.setFixedSize(16, row_height - 2)
            button.setAutoRepeat(True)
            button.setFocusPolicy(QtCore.Qt.NoFocus)
        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll_area.setMinimumWidth(0)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QHBoxLayout(self.content)
        self.content_layout.setContentsMargins(1, 1, 1, 1)
        self.content_layout.setSpacing(3)
        self.content_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
        self.scroll_area.setWidget(self.content)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.scroll_area, 1)
        layout.addWidget(self.next_button)
        self.previous_button.clicked.connect(lambda: self._scroll(-1))
        self.next_button.clicked.connect(lambda: self._scroll(1))
        scrollbar = self.scroll_area.horizontalScrollBar()
        scrollbar.rangeChanged.connect(self._update_arrows)
        scrollbar.valueChanged.connect(self._update_arrows)
        self.scroll_area.viewport().installEventFilter(self)
        self._update_arrows()

    def add_button(self, button):
        button.setFixedHeight(self.height() - 4)
        button.installEventFilter(self)
        self.content_layout.addWidget(button)

    def _scroll(self, direction):
        bar = self.scroll_area.horizontalScrollBar()
        bar.setValue(bar.value() + direction * max(40, self.scroll_area.viewport().width() // 2))

    def _update_arrows(self, *args):
        bar = self.scroll_area.horizontalScrollBar()
        self.previous_button.setEnabled(bar.value() > bar.minimum())
        self.next_button.setEnabled(bar.value() < bar.maximum())

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.FocusIn and isinstance(watched, QtWidgets.QToolButton):
            self.scroll_area.ensureWidgetVisible(watched, 4, 0)
        elif event.type() == QtCore.QEvent.Wheel:
            delta = event.angleDelta().x() or event.angleDelta().y()
            if delta:
                self._scroll(-1 if delta > 0 else 1)
                event.accept()
                return True
        return super().eventFilter(watched, event)


class ModelSearchEdit(QtWidgets.QLineEdit):
    navigateRequested = QtCore.Signal(int)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.navigateRequested.emit(-1 if event.modifiers() & QtCore.Qt.ShiftModifier else 1)
            event.accept()
            return
        if event.key() == QtCore.Qt.Key_Escape:
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


class ModeHotbox(QtWidgets.QFrame):
    modeChosen = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setObjectName("modeHotbox")
        self.setStyleSheet(
            "#modeHotbox { background: #171a1f; border: 1px solid #59616d; "
            "border-radius: 10px; } "
            "QLabel { color: #aeb7c2; } "
            "QPushButton { min-width: 150px; min-height: 64px; "
            "font-size: 15px; font-weight: 600; padding: 8px; }"
        )
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("KyMol mode")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        choices = QtWidgets.QHBoxLayout()
        self.object_mode_button = QtWidgets.QPushButton("←  Object mode")
        self.chain_mode_button = QtWidgets.QPushButton("Chain mode  →")
        self.object_mode_button.clicked.connect(lambda: self._choose("object"))
        self.chain_mode_button.clicked.connect(lambda: self._choose("chain"))
        choices.addWidget(self.object_mode_button)
        choices.addWidget(self.chain_mode_button)
        layout.addLayout(choices)

    def _choose(self, mode):
        self.modeChosen.emit(mode)
        self.hide()

    def show_centered(self, parent):
        self.adjustSize()
        center = parent.mapToGlobal(parent.rect().center())
        self.move(center - self.rect().center())
        self.show()
        self.raise_()
        self.setFocus()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Left:
            self._choose("object")
            return
        if event.key() == QtCore.Qt.Key_Right:
            self._choose("chain")
            return
        if event.key() == QtCore.Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)


class KYMolDialog(QtWidgets.QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.mode = "chain"
        self._search_matches = []
        self._search_index = -1
        self.selected_chains = {}
        self._chain_visual_cache = {}
        self._chain_buttons = {}
        self._chain_refresh_cursor = 0
        self.is_pinned = False
        self.setWindowTitle("KyMol — Structure Review")
        flags = self.windowFlags()
        flags |= QtCore.Qt.WindowMinimizeButtonHint
        flags &= ~QtCore.Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(500, 400)
        self.resize(820, 620)
        self._build_ui()
        self.mode_hotbox = ModeHotbox(self)
        self.mode_hotbox.modeChosen.connect(self._set_mode)
        self._install_shortcuts()
        self.refresh_objects(keep_selection=True)
        self.chain_visual_timer = QtCore.QTimer(self)
        self.chain_visual_timer.setInterval(CHAIN_VISUAL_REFRESH_INTERVAL_MS)
        self.chain_visual_timer.timeout.connect(self._refresh_chain_visuals)
        self.chain_visual_timer.start()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        outer_layout = layout
        top_actions = QtWidgets.QHBoxLayout()
        self.mode_hint = QtWidgets.QLabel("Models")
        self.chain_mode_toggle = QtWidgets.QCheckBox("Show chains")
        self.chain_mode_toggle.setChecked(True)
        self.chain_mode_toggle.setToolTip("Show chain selection tools. Tab in the model list also opens the mode menu.")
        self.chain_mode_toggle.toggled.connect(lambda checked: self._set_mode("chain" if checked else "object"))
        self.undo_button = QtWidgets.QToolButton()
        self.undo_button.setText("↶")
        self.undo_button.setToolTip("Undo (Ctrl+Z)")
        self.redo_button = QtWidgets.QToolButton()
        self.redo_button.setText("↷")
        self.redo_button.setToolTip("Redo (Ctrl+Shift+Z / Ctrl+Y)")
        self.pin_button = QtWidgets.QToolButton()
        self.pin_button.setText("📌")
        self.pin_button.setCheckable(True)
        self.pin_button.setToolTip("Keep this panel always on top")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self.pin_button.clicked.connect(self.toggle_pin)
        top_actions.addWidget(self.mode_hint)
        top_actions.addWidget(self.chain_mode_toggle)
        top_actions.addStretch(1)
        top_actions.addWidget(self.undo_button)
        top_actions.addWidget(self.redo_button)
        top_actions.addWidget(self.pin_button)
        layout.addLayout(top_actions)

        selection_help = (
            "Click / Ctrl / Shift: select models. <b>Gold: active target.</b> "
            "Drag models into groups. Drag the divider below the list to resize."
        )
        self.mode_hint.setToolTip(selection_help)

        self.content_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(8)
        self.content_splitter.setStyleSheet("QSplitter::handle { background: #c4cbd1; }")
        self.content_splitter.setToolTip("Drag the divider to resize the model list and tools")
        self.model_pane = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.model_pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.content_splitter.addWidget(self.model_pane)
        outer_layout.addWidget(self.content_splitter, 1)

        search_line = QtWidgets.QHBoxLayout()
        self.search_edit = ModelSearchEdit()
        self.search_edit.setPlaceholderText("Search models (Ctrl+F)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setToolTip("Find model names without changing selection or visibility. Enter: next; Shift+Enter: previous.")
        self.search_count = QtWidgets.QLabel("0 / 0")
        self.search_count.setMinimumWidth(50)
        self.search_count.setAlignment(QtCore.Qt.AlignCenter)
        self.search_previous_button = QtWidgets.QToolButton()
        self.search_previous_button.setText("↑")
        self.search_previous_button.setToolTip("Previous match (Shift+Enter)")
        self.search_next_button = QtWidgets.QToolButton()
        self.search_next_button.setText("↓")
        self.search_next_button.setToolTip("Next match (Enter)")
        self.search_previous_button.setEnabled(False)
        self.search_next_button.setEnabled(False)
        self.search_edit.textChanged.connect(lambda: self._update_search())
        self.search_edit.navigateRequested.connect(self._step_search)
        self.search_previous_button.clicked.connect(lambda: self._step_search(-1))
        self.search_next_button.clicked.connect(lambda: self._step_search(1))
        search_line.addWidget(self.search_edit, 1)
        search_line.addWidget(self.search_count)
        search_line.addWidget(self.search_previous_button)
        search_line.addWidget(self.search_next_button)
        layout.addLayout(search_line)

        self.object_list = ObjectGroupTree()
        self.object_list.setToolTip(selection_help)
        self.object_list.setMinimumHeight(96)
        self.object_list.setItemDelegate(ActiveObjectDelegate(self.object_list))
        self.object_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.object_list.currentItemChanged.connect(self._on_current_item_changed)
        self.object_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.object_list.objectsDropped.connect(self._move_objects_to_group)
        self.object_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.object_list.customContextMenuRequested.connect(
            self._show_object_context_menu
        )
        layout.addWidget(self.object_list, 1)

        self.chain_actions = QtWidgets.QFrame()
        chain_actions_layout = QtWidgets.QHBoxLayout(self.chain_actions)
        chain_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.chain_selection_label = QtWidgets.QLabel("No chains selected")
        self.copy_chains_button = QtWidgets.QPushButton("Copy chains")
        self.cut_chains_button = QtWidgets.QPushButton("Cut chains")
        self.copy_chains_button.clicked.connect(
            lambda: self._transform_selected_chains(cut=False)
        )
        self.cut_chains_button.clicked.connect(
            lambda: self._transform_selected_chains(cut=True)
        )
        chain_actions_layout.addWidget(self.chain_selection_label, 1)
        chain_actions_layout.addWidget(self.copy_chains_button)
        chain_actions_layout.addWidget(self.cut_chains_button)
        layout.addWidget(self.chain_actions)

        self.tools_scroll = QtWidgets.QScrollArea()
        self.tools_scroll.setWidgetResizable(True)
        self.tools_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.tools_scroll.setMinimumSize(0, 60)
        self.tools_scroll.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding)
        self.tools_pane = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.tools_pane)
        layout.setContentsMargins(0, 4, 4, 0)
        self.tools_scroll.setWidget(self.tools_pane)
        self.content_splitter.addWidget(self.tools_scroll)
        self.content_splitter.setStretchFactor(0, 3)
        self.content_splitter.setStretchFactor(1, 2)
        self.content_splitter.setSizes([290, 230])

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
        self.create_group_button.clicked.connect(self.create_group)
        object_edit_actions.addWidget(self.create_group_button)
        object_edit_actions.addStretch(1)
        layout.addLayout(object_edit_actions)

        chain_line = QtWidgets.QHBoxLayout()
        chain_line.addWidget(QtWidgets.QLabel("Target chain (optional):"))
        self.chain_edit = QtWidgets.QLineEdit()
        self.chain_edit.setPlaceholderText("e.g. A")
        self.chain_edit.setMaximumWidth(100)
        chain_line.addWidget(self.chain_edit)
        chain_line.addStretch(1)
        layout.addLayout(chain_line)

        align_settings = QtWidgets.QHBoxLayout()
        self.method_combo = QtWidgets.QComboBox()
        self.method_combo.addItems(["align", "super", "cealign"])
        self.scope_combo = QtWidgets.QComboBox()
        self.scope_combo.addItem("Auto: best sequence-matching chain", "auto")
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
        self.visibility_button = QtWidgets.QPushButton("Toggle selected visibility (H)")
        self.only_button = QtWidgets.QPushButton("Only selected (/)")
        self.show_all_button = QtWidgets.QPushButton("Show all (Alt+H)")
        self.focus_button = QtWidgets.QPushButton("Focus active (F)")
        self.visibility_button.clicked.connect(self.toggle_visibility)
        self.only_button.clicked.connect(lambda: self.display_selected("only"))
        self.show_all_button.clicked.connect(self.show_all_objects)
        self.focus_button.clicked.connect(self.focus_active)
        display_grid.addWidget(self.visibility_button, 0, 0)
        display_grid.addWidget(self.only_button, 0, 1)
        display_grid.addWidget(self.show_all_button, 1, 0)
        display_grid.addWidget(self.focus_button, 1, 1)
        layout.addLayout(display_grid)

        export_mode_line = QtWidgets.QHBoxLayout()
        self.export_mode = QtWidgets.QComboBox()
        self.export_mode.addItem("Active model only (gold) / chain field", True)
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

        source_actions = QtWidgets.QHBoxLayout()
        self.source_button = QtWidgets.QPushButton("Associate source…")
        self.source_button.setToolTip(
            "Choose the original file for the active model if its source is unknown. "
            "This records your association; it does not verify structural identity."
        )
        self.source_button.clicked.connect(self.associate_source)
        source_actions.addWidget(self.source_button)
        source_actions.addStretch(1)
        layout.addLayout(source_actions)

        self.sequence_preview = QtWidgets.QPlainTextEdit()
        self.sequence_preview.setReadOnly(True)
        self.sequence_preview.setPlaceholderText(
            "The active object's FASTA sequence will appear here and be copied to the clipboard."
        )
        self.sequence_preview.setMaximumHeight(110)
        self.sequence_preview.setMinimumHeight(60)
        layout.addWidget(self.sequence_preview)

        self.status = QtWidgets.QPlainTextEdit("KyMol is ready.")
        self.status.setReadOnly(True)
        self.status.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self.status.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.status.setFixedHeight(STATUS_PANEL_HEIGHT)
        self.status.setToolTip(
            "Current KyMol status. Scroll here when a message is longer than the panel."
        )
        self.status.setStyleSheet(
            "QPlainTextEdit { padding: 6px; background: #20242a; color: #e8edf2; "
            "border: 0; border-radius: 3px; }"
        )
        outer_layout.addWidget(self.status)

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
        self.hide_shortcut.activated.connect(self.toggle_visibility)
        self.show_all_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence("Alt+H"), self.object_list
        )
        self.show_all_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
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
        self.focus_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("F"), self.object_list)
        self.focus_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.focus_shortcut.activated.connect(self.focus_active)
        self.mode_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Tab"), self.object_list)
        self.mode_shortcut.setContext(QtCore.Qt.WidgetShortcut)
        self.mode_shortcut.activated.connect(self.show_mode_hotbox)
        self.search_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self._focus_search)
        self.undo_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+Z"), self
        )
        self.undo_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.undo_shortcut.activated.connect(lambda: self._history_shortcut(redo=False))
        self.redo_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+Shift+Z"), self
        )
        self.redo_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.redo_shortcut.activated.connect(lambda: self._history_shortcut(redo=True))
        self.redo_y_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+Y"), self
        )
        self.redo_y_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        self.redo_y_shortcut.activated.connect(lambda: self._history_shortcut(redo=True))

    def _history_shortcut(self, redo=False):
        focused = QtWidgets.QApplication.focusWidget()
        if isinstance(focused, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)) and not focused.isReadOnly():
            (focused.redo if redo else focused.undo)()
            return
        (self.redo if redo else self.undo)()

    def show_mode_hotbox(self):
        if self.mode_hotbox.isVisible():
            self.mode_hotbox.hide()
        else:
            self.mode_hotbox.show_centered(self)

    def _focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _update_search(self, preserve_match=False):
        old_match = (
            self._search_matches[self._search_index]
            if preserve_match and 0 <= self._search_index < len(self._search_matches)
            else None
        )
        query = self.search_edit.text().strip().casefold()
        self._search_matches = [
            item.data(0, QtCore.Qt.UserRole)
            for item in self.object_list.object_items()
            if query and query in item.text(0).casefold()
        ]
        self._search_index = (
            self._search_matches.index(old_match)
            if old_match in self._search_matches
            else (0 if self._search_matches else -1)
        )
        self._show_search_match()

    def _step_search(self, direction):
        if self._search_matches:
            self._search_index = (self._search_index + direction) % len(self._search_matches)
            self._show_search_match()

    def _show_search_match(self):
        """Search has its own cursor; it must never setCurrentItem or select."""
        matches = set(self._search_matches)
        current = self._search_matches[self._search_index] if self._search_index >= 0 else None
        for item in self.object_list.object_items():
            name = item.data(0, QtCore.Qt.UserRole)
            item.setData(0, SEARCH_MATCH_ROLE, name in matches)
            item.setData(0, SEARCH_CURRENT_ROLE, name == current)
            if name == current:
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.object_list.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtCenter)
        self.search_count.setText("{} / {}".format(self._search_index + 1, len(matches)))
        self.search_count.setToolTip(current or "No matching model")
        self.search_previous_button.setEnabled(bool(matches))
        self.search_next_button.setEnabled(bool(matches))
        self.object_list.viewport().update()

    def _set_mode(self, mode):
        if mode not in ("object", "chain"):
            return
        self.mode = mode
        self.chain_mode_toggle.blockSignals(True)
        self.chain_mode_toggle.setChecked(mode == "chain")
        self.chain_mode_toggle.blockSignals(False)
        self.object_list.setColumnHidden(1, mode != "chain")
        self.chain_actions.setVisible(mode == "chain")
        self.refresh_objects(keep_selection=True)
        self._set_status(
            "Chain mode: select colored chain tiles."
            if mode == "chain"
            else self.controller.status_text()
        )

    def undo(self):
        def action():
            description = self.controller.undo()
            self.refresh_objects(keep_selection=True)
            return description

        self._run(action)

    def redo(self):
        def action():
            description = self.controller.redo()
            self.refresh_objects(keep_selection=True)
            return description

        self._run(action)

    def toggle_pin(self):
        self.is_pinned = not self.is_pinned
        geometry = self.saveGeometry()
        was_visible = self.isVisible()
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, self.is_pinned)
        self.restoreGeometry(geometry)
        self.pin_button.setChecked(self.is_pinned)
        self.pin_button.setToolTip(
            "Unpin this panel"
            if self.is_pinned
            else "Keep this panel always on top"
        )
        if was_visible:
            self.show()
            self.raise_()

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
        self.status.setPlainText(message)
        self.status.verticalScrollBar().setValue(0)
        color = "#7f1d1d" if error else "#20242a"
        self.status.setStyleSheet(
            "QPlainTextEdit { padding: 6px; background: %s; color: #e8edf2; "
            "border: 0; border-radius: 3px; }" % color
        )

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
        expanded_groups = {
            self.object_list.topLevelItem(index).text(0): self.object_list.topLevelItem(index).isExpanded()
            for index in range(self.object_list.topLevelItemCount())
            if self.object_list.topLevelItem(index).data(0, ITEM_KIND_ROLE) == GROUP_KIND
        }
        self.object_list.blockSignals(True)
        self.object_list.clear()
        objects = self.controller.molecular_objects()
        self._chain_buttons = {}
        self._chain_visual_cache = {
            key: state
            for key, state in self._chain_visual_cache.items()
            if self.mode == "chain" and key[0] in objects
        }
        self.selected_chains = {
            name: chains
            for name, chains in self.selected_chains.items()
            if name in objects
        }
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
                self._attach_chain_widget(item, name)
                self._restore_item_state(item, name, selected, active)
            group_item.setExpanded(expanded_groups.get(group_name, True))
        for name in objects:
            if name in grouped:
                continue
            item = self._new_object_item(name)
            self.object_list.addTopLevelItem(item)
            self._attach_chain_widget(item, name)
            self._restore_item_state(item, name, selected, active)
        self.object_list.blockSignals(False)
        self._on_selection_changed()
        self._apply_active_style()
        self._update_chain_selection_label()
        self._update_search(preserve_match=True)
        self._chain_refresh_cursor = 0
        if self.mode == "chain" and self._chain_buttons:
            first_object = next(iter(self._chain_buttons))[0]
            self._refresh_chain_object(first_object)

    def _new_object_item(self, name):
        item = QtWidgets.QTreeWidgetItem([name])
        item.setToolTip(0, name)
        item.setData(0, QtCore.Qt.UserRole, name)
        item.setData(0, ITEM_KIND_ROLE, OBJECT_KIND)
        item.setFlags(
            QtCore.Qt.ItemIsEnabled
            | QtCore.Qt.ItemIsSelectable
            | QtCore.Qt.ItemIsDragEnabled
        )
        return item

    def _attach_chain_widget(self, item, name):
        if self.mode != "chain":
            return
        chains = list(self.controller.cmd.get_chains(name))
        valid = set(chains)
        selected = set(self.selected_chains.get(name, [])) & valid
        if selected:
            self.selected_chains[name] = [
                chain for chain in chains if chain in selected
            ]
        else:
            self.selected_chains.pop(name, None)
        row_height = max(28, self.object_list.fontMetrics().height() + 10)
        widget = ChainStrip(row_height, self.object_list)
        for chain in chains:
            button = QtWidgets.QToolButton(widget.content)
            button.setText(chain or "∅")
            button.setCheckable(True)
            button.setAccessibleName("{}: chain {}".format(name, chain or "blank"))
            button.setChecked(chain in selected)
            self._chain_buttons[(name, chain)] = button
            self._apply_chain_visual(button, name, chain)
            button.toggled.connect(
                lambda checked, object_name=name, chain_name=chain:
                self._toggle_chain(object_name, chain_name, checked)
            )
            widget.add_button(button)
        widget.content_layout.addStretch(1)
        self.object_list.setItemWidget(item, 1, widget)

    def _apply_chain_visual(self, button, object_name, chain):
        state = self._chain_visual_cache.get((object_name, chain))
        color = state.color_hex if state else chain_swatch(chain)
        hidden = bool(state.hidden) if state else False
        text_color = contrast_text_color(color)
        button.setProperty("chainColor", color)
        button.setProperty("chainHidden", hidden)
        button.setProperty("chainVisualKnown", state is not None)
        button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        button.setIcon(
            hidden_chain_icon(text_color) if hidden else QtGui.QIcon()
        )
        button.setIconSize(QtCore.QSize(14, 14))
        visibility = ("hidden" if hidden else "visible") if state else "color / visibility pending"
        button.setToolTip(
            "{} · chain {} · {} in PyMOL".format(
                object_name, chain or "(blank)", visibility
            )
        )
        # Put the full-label minimum into the stylesheet itself. A later polish
        # (after insertion into the tree, or on a mode rebuild) reapplies CSS
        # constraints and would replace a separate setMinimumWidth() override.
        button.ensurePolished()
        label_font = QtGui.QFont(button.font())
        label_font.setWeight(QtGui.QFont.DemiBold)
        text_width = QtGui.QFontMetrics(label_font).horizontalAdvance(button.text())
        minimum_content_width = max(20, text_width + 18)
        button.setStyleSheet(
            "QToolButton {{ background: {0}; color: {1}; "
            "border: 1px solid transparent; border-radius: 3px; "
            "font-weight: 600; min-width: {2}px; "
            "padding: 0 4px; }} "
            "QToolButton:checked {{ border-color: #ffffff; "
            "background: {0}; }}".format(color, text_color, minimum_content_width)
        )

    def _refresh_chain_object(self, object_name):
        try:
            states = self.controller.chain_visual_states([object_name])
        except Exception:
            return False
        self._chain_visual_cache = {
            key: state
            for key, state in self._chain_visual_cache.items()
            if key[0] != object_name
        }
        self._chain_visual_cache.update(states)
        for (button_object, chain), button in self._chain_buttons.items():
            if button_object == object_name and (button_object, chain) in states:
                self._apply_chain_visual(button, button_object, chain)
        return True

    def _refresh_chain_visuals(self):
        if (
            not self.isVisible()
            or not self.isActiveWindow()
            or self.mode != "chain"
            or not self._chain_buttons
        ):
            return
        object_names = list(dict.fromkeys(
            object_name for object_name, _ in self._chain_buttons
        ))
        index = self._chain_refresh_cursor % len(object_names)
        self._chain_refresh_cursor = (index + 1) % len(object_names)
        self._refresh_chain_object(object_names[index])

    def _toggle_chain(self, object_name, chain, checked):
        selected = self.selected_chains.setdefault(object_name, [])
        if checked and chain not in selected:
            selected.append(chain)
        elif not checked and chain in selected:
            selected.remove(chain)
        if not selected:
            self.selected_chains.pop(object_name, None)
        self._update_chain_selection_label()

    def _update_chain_selection_label(self):
        count = sum(len(chains) for chains in self.selected_chains.values())
        self.chain_selection_label.setText(
            "{} chain(s) selected".format(count) if count else "No chains selected"
        )
        self.copy_chains_button.setEnabled(bool(count))
        self.cut_chains_button.setEnabled(bool(count))

    def _transform_selected_chains(self, cut=False):
        chain_map = {
            name: list(chains)
            for name, chains in self.selected_chains.items()
            if chains
        }
        if not chain_map:
            self._set_status("Select one or more chain tiles first.", error=True)
            return
        requested_name = ""
        if len(chain_map) == 1:
            object_name, chains = next(iter(chain_map.items()))
            operation_name = "cut" if cut else "copy"
            default_name = self.controller._unique_object_name(
                self.controller._default_chain_result_name(
                    object_name, chains, operation_name
                )
            )
            requested_name, accepted = QtWidgets.QInputDialog.getText(
                self,
                "{} selected chains".format("Cut" if cut else "Copy"),
                "New object name:",
                QtWidgets.QLineEdit.Normal,
                default_name,
            )
            if not accepted:
                return

        def action():
            transform = (
                self.controller.cut_chains if cut else self.controller.copy_chains
            )
            created = transform(chain_map, requested_name=requested_name)
            self.selected_chains.clear()
            self.refresh_objects(keep_selection=True)
            self._update_chain_selection_label()
            return created

        self._run(action)

    def _restore_item_state(self, item, name, selected, active):
        if name == active:
            self.object_list._set_current_without_selecting(item)
        if name in selected:
            item.setSelected(True)

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

    def _show_object_context_menu(self, position):
        item = self.object_list.itemAt(position)
        if item is None or item.data(0, ITEM_KIND_ROLE) != OBJECT_KIND:
            return
        if not item.isSelected():
            self.object_list.select_exclusive(item)
        else:
            self.object_list._set_current_without_selecting(item)
        menu = QtWidgets.QMenu(self.object_list)
        rename_action = menu.addAction("Rename (F2)")
        delete_action = menu.addAction("Delete selected (X / Del)")
        chosen = menu.exec_(self.object_list.viewport().mapToGlobal(position))
        if chosen is rename_action:
            self.rename_active()
        elif chosen is delete_action:
            self.delete_selected()

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

    def toggle_visibility(self):
        group_name = self._current_group()
        if group_name:
            self._run(lambda: self.controller.toggle_group_visibility(group_name))
        else:
            self._run(self.controller.toggle_selected_visibility)

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
            "Create KyMol group",
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
        active = self.controller.state.active
        whole_chain, chain = self._export_selection()
        try:
            export_selection = self.controller.active_selection(whole_chain, chain)
            atom_identity = tuple(self.controller.cmd.index(export_selection))
            suggestion = self.controller.sources.export_default(
                active, file_format, getattr(self, "_last_export_directory", "")
            )
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return
        self._set_status("Exporting active model '{}'. {}\n{}".format(
            active, suggestion.reason, suggestion.directory))
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export active {}: {}".format(file_format.upper(), active), suggestion.path,
            "{} files (*.{})".format(file_format.upper(), file_format),
        )
        if not filename:
            return
        if not filename.lower().endswith("." + file_format):
            filename += "." + file_format
        if self.controller.sources.is_source_path(filename):
            self._set_status("This is an original source file. Choose a new export filename to preserve it.", error=True)
            return
        # Confirm the final path too: adding a missing extension can target a file
        # which the platform's save picker did not include in its overwrite check.
        if os.path.exists(filename):
            answer = QtWidgets.QMessageBox.question(
                self, "Replace existing export?", "Replace this existing export file?\n\n" + filename,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
        def save_reviewed_selection():
            if self.controller.state.active != active:
                raise KYMolError("The active model changed while the export dialog was open. "
                                 "Export again to confirm the new target.")
            current_selection = self.controller.active_selection(whole_chain, chain)
            if tuple(self.controller.cmd.index(current_selection)) != atom_identity:
                raise KYMolError("The model or selected atoms changed while the export dialog was open. "
                                 "Export again to confirm the selection.")
            return self.controller.export_active(filename, file_format, whole_chain, chain)

        result = self._run(save_reviewed_selection)
        if result is not None:
            self._last_export_directory = os.path.dirname(os.path.abspath(filename))
            self._set_status("Exported active model '{}' to:\n{}".format(active, filename))

    def associate_source(self):
        active = self.controller.state.active
        if active not in self.controller.molecular_objects():
            self._set_status("Select an active model before associating its source.", error=True)
            return
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose the known original file for: " + active,
            getattr(self, "_last_export_directory", ""),
            "Structure files (*.pdb *.cif *.mmcif *.pdb.gz *.cif.gz);;All files (*)",
        )
        if not filename:
            return
        result = self._run(lambda: self.controller.sources.associate_source(active, filename))
        if result is not None:
            self._set_status("Source associated by you for '{}':\n{}\n"
                             "Structural identity was not checked.".format(active, filename))

    def copy_fasta(self):
        whole_chain, chain = self._export_selection()
        def action():
            fasta = self.controller.fasta_active(whole_chain, chain)
            self.sequence_preview.setPlainText(fasta)
            QtWidgets.QApplication.clipboard().setText(fasta)
            self._set_status("Copied FASTA to clipboard. " + self.controller.status_text())
        self._run(action)
