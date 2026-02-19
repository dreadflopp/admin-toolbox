"""
Common components shared across window modules.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QFrame,
    QPushButton,
    QLineEdit,
    QSizePolicy,
    QProgressBar,
    QHeaderView,
    QColorDialog,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor, QBrush

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    HAS_WEBENGINE = True

    class MapPage(QWebEnginePage):
        """Custom page to intercept toolbox:pin-X navigation."""
        pinClicked = Signal(int)

        def acceptNavigationRequest(self, url, _type, isMainFrame):
            if url.scheme() == "toolbox":
                # Path is "pin-X" for toolbox:pin-X (opaque URL, host is empty)
                path = url.path().strip()
                if path.startswith("pin-"):
                    try:
                        pid = int(path[4:].strip())
                        self.pinClicked.emit(pid)
                    except ValueError:
                        pass
                    return False
            return super().acceptNavigationRequest(url, _type, isMainFrame)
except ImportError:
    HAS_WEBENGINE = False
    MapPage = None

MARKER_INDEX_ROLE = Qt.ItemDataRole.UserRole + 100
VISIT_ROLE = Qt.ItemDataRole.UserRole + 101  # (slinga, trip_idx, visit_idx) for routes table

# Colors for customer table selection (exclude color column)
SELECTION_BG = "#bbdefb"
SELECTION_TEXT = "#323130"

CUSTOM_PIN_ID_BASE = 100000


class CustomerTableDelegate(QStyledItemDelegate):
    """Delegate for customer table: no selection/hover on color column (0), black text when selected."""

    def __init__(self, table, parent=None):
        super().__init__(parent)
        self._table = table

    def paint(self, painter, option, index):
        from PySide6.QtWidgets import QStyle

        col = index.column()
        is_color_col = col == 0
        is_selected = (option.state & QStyle.StateFlag.State_Selected) != 0

        if is_color_col:
            # Color column: always use item background, no selection/hover
            bg = index.data(Qt.ItemDataRole.BackgroundRole)
            if bg is not None:
                painter.fillRect(option.rect, bg)
            opt = QStyleOptionViewItem(option)
            opt.state &= ~QStyle.StateFlag.State_Selected
            super().paint(painter, opt, index)
        else:
            opt = QStyleOptionViewItem(option)
            if is_selected:
                opt.backgroundBrush = QBrush(QColor(SELECTION_BG))
                opt.palette.setColor(opt.palette.ColorGroup.Current, opt.palette.ColorRole.Highlight, QColor(SELECTION_BG))
                opt.palette.setColor(opt.palette.ColorGroup.Current, opt.palette.ColorRole.HighlightedText, QColor(SELECTION_TEXT))
            super().paint(painter, opt, index)


class CollapsibleSection(QFrame):
    """A collapsible section with clickable header (arrow + title)."""

    def __init__(self, title: str, parent=None, header_widgets=None, initial_expanded: bool = True, header_color: str = None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(4, 4, 4, 4)
        header_layout.setSpacing(4)
        self._arrow_btn = QPushButton("\u25BE" if initial_expanded else "\u25B8")  # ▾ ▸ same-size arrows
        self._arrow_btn.setFixedSize(28, 28)
        self._arrow_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._arrow_btn.setFlat(True)
        self._arrow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #323130; font-size: 14pt; font-family: 'Segoe UI Symbol', sans-serif; "
            "padding: 0; border: none; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; } "
            "QPushButton:hover { background: transparent; color: #6c6c6c; }"
        )
        self._arrow_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._arrow_btn)
        if header_color:
            color_dot = QFrame()
            color_dot.setFixedSize(14, 14)
            color_dot.setStyleSheet(f"background-color: {header_color}; border: 1px solid #888; border-radius: 7px;")
            header_layout.addWidget(color_dot)
        header_layout.addWidget(QLabel(title))
        if header_widgets:
            for w in header_widgets:
                header_layout.addWidget(w)
        header_layout.addStretch()
        layout.addWidget(header_row)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 0, 4, 4)
        layout.addWidget(self._content)
        self._expanded = initial_expanded
        self._content.setVisible(initial_expanded)
        self._title = title

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow_btn.setText("\u25BE" if self._expanded else "\u25B8")  # ▾ ▸

    def set_expanded(self, expanded: bool):
        if self._expanded != expanded:
            self._toggle()

    def content_layout(self):
        return self._content_layout


class CustomAddressesSection(QFrame):
    """
    Section for adding custom addresses with geocoding.
    Input field, color chooser, table. Geocodes in background, adds pin when found.
    """

    def __init__(self, add_pin_fn, remove_pin_fn, log_fn=None, parent=None):
        super().__init__(parent)
        self._add_pin_fn = add_pin_fn
        self._remove_pin_fn = remove_pin_fn
        self._log = log_fn or (lambda msg, lvl="info": None)
        self._custom_pins = []  # [(pin_id, address, color, lat, lng), ...]
        self._next_pin_id = CUSTOM_PIN_ID_BASE
        self._on_custom_row_selected_fn = None
        self._geocode_thread = None

        self.setObjectName("customAddressesSection")
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setStyleSheet("""
            QFrame#customAddressesSection {
                background-color: #ffffff;
                border: 1px solid #edebe9;
                border-radius: 8px;
            }
            QFrame#customAddressesSection QTableWidget#customAddressesTable::item {
                selection-background-color: #bbdefb;
            }
            QFrame#customAddressesSection QTableWidget#customAddressesTable::item:hover {
                background-color: #e3f2fd;
            }
            QFrame#customAddressesSection QPushButton#deleteCellLbl {
                background: transparent;
                border: none;
                color: #c62828;
                font-size: 9pt;
                padding: 0;
                min-width: 0;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        row = QHBoxLayout()
        self._address_edit = QLineEdit()
        self._address_edit.setPlaceholderText("Enter address...")
        self._address_edit.returnPressed.connect(self._on_add)
        row.addWidget(self._address_edit)

        self._busy_indicator = QProgressBar()
        self._busy_indicator.setRange(0, 0)
        self._busy_indicator.setFixedSize(22, 22)
        self._busy_indicator.setTextVisible(False)
        self._busy_indicator.setVisible(False)
        row.addWidget(self._busy_indicator)

        self._color_btn = QPushButton()
        self._color = "#ff8c00"
        self._update_color_btn()
        self._color_btn.clicked.connect(self._choose_color)
        self._color_btn.setFixedSize(28, 28)
        row.addWidget(self._color_btn)

        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._on_add)
        row.addWidget(btn_add)
        layout.addLayout(row)

        self._table = QTableWidget()
        self._table.setObjectName("customAddressesTable")
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Color", "Address", ""])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().resizeSection(0, 40)
        self._table.horizontalHeader().resizeSection(2, 26)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setMinimumHeight(24)
        self._table.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._table.setVisible(False)
        self._table.itemSelectionChanged.connect(self._on_custom_table_selection_changed)
        self._table_in_layout = False
        self._main_layout = layout

    def _update_color_btn(self):
        self._color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self._color}; border: 1px solid #888; border-radius: 4px; }}"
        )

    def _choose_color(self):
        qcolor = QColorDialog.getColor(QColor(self._color), self, "Choose color")
        if qcolor.isValid():
            self._color = qcolor.name()
            self._update_color_btn()

    def set_callbacks(self, on_custom_row_selected_fn):
        """Set callback for when custom row is selected: fn(lat, lng, pin_id)."""
        self._on_custom_row_selected_fn = on_custom_row_selected_fn

    def clear_selection(self):
        """Clear table selection (called by parent when main table is selected)."""
        self._table.clearSelection()

    def select_row_by_pin_id(self, pin_id: int) -> bool:
        """Select the row for the given pin_id. Returns True if found."""
        for i, (pid, _, _, _, _) in enumerate(self._custom_pins):
            if pid == pin_id:
                self._table.selectRow(i)
                self._table.scrollTo(self._table.model().index(i, 0))
                return True
        return False

    def get_pin_coords(self, pin_id: int) -> tuple[float, float] | None:
        """Return (lat, lng) for the given pin_id, or None."""
        for pid, _, _, lat, lng in self._custom_pins:
            if pid == pin_id:
                return (lat, lng)
        return None

    def _set_error_border(self, on: bool):
        self._address_edit.setStyleSheet("border: 2px solid red;" if on else "")

    def _on_add(self):
        addr = (self._address_edit.text() or "").strip()
        if not addr:
            return
        self._set_error_border(False)
        self._busy_indicator.setVisible(True)
        self._address_edit.clear()
        self._add_address_async(addr, self._color)

    def _add_address_async(self, address: str, color: str):
        from utils import _geocode_one, load_google_maps_api_key

        class GeocodeWorker(QThread):
            finished_with_coords = Signal(float, float)
            finished_failed = Signal()

            def __init__(self, addr, api_key, log_fn):
                super().__init__()
                self._addr = addr
                self._api_key = api_key
                self._log_fn = log_fn

            def run(self):
                coords = _geocode_one(self._addr, self._api_key, self._log_fn)
                if coords:
                    self.finished_with_coords.emit(coords[0], coords[1])
                else:
                    self.finished_failed.emit()

        api_key = load_google_maps_api_key()
        self._geocode_thread = GeocodeWorker(address, api_key, self._log)
        self._geocode_thread.finished_with_coords.connect(
            lambda lat, lng: self._on_geocode_ok(address, color, lat, lng)
        )
        self._geocode_thread.finished_failed.connect(lambda: self._on_geocode_failed(address))
        self._geocode_thread.start()

    def _on_geocode_ok(self, address: str, color: str, lat: float, lng: float):
        self._busy_indicator.setVisible(False)
        self._set_error_border(False)
        pin_id = self.get_next_pin_id()
        self._add_pin_fn(address, color, lat, lng, pin_id)
        self._custom_pins.append((pin_id, address, color, lat, lng))
        row = self._table.rowCount()
        if not self._table_in_layout:
            self._table_in_layout = True
            self._main_layout.addWidget(self._table, 0)
        self._table.insertRow(row)
        color_item = QTableWidgetItem()
        color_item.setBackground(QBrush(QColor(color)))
        color_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self._table.setItem(row, 0, color_item)
        addr_item = QTableWidgetItem(address)
        addr_item.setData(MARKER_INDEX_ROLE, pin_id)
        self._table.setItem(row, 1, addr_item)
        btn_del = QPushButton("Del")
        btn_del.setObjectName("deleteCellLbl")
        btn_del.setFlat(True)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(lambda checked, pid=pin_id: self._remove_address(pid))
        cell_widget = QWidget()
        cell_layout = QHBoxLayout(cell_widget)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cell_layout.addWidget(btn_del)
        cell_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        row_bg = "#f5f5f5" if row % 2 == 1 else "#ffffff"
        cell_widget.setStyleSheet(f"background: {row_bg};")
        self._table.setCellWidget(row, 2, cell_widget)
        self._table.resizeRowsToContents()
        self._update_table_height()
        self._table.setVisible(True)
        self._log(f"Custom address added: {address[:50]}...", "info")

    def _on_geocode_failed(self, address: str):
        self._busy_indicator.setVisible(False)
        self._set_error_border(True)
        self._address_edit.setText(address)
        self._address_edit.setFocus()
        self._log(f"Custom address not found: {address[:50]}...", "warn")

    def _remove_address(self, pin_id: int) -> None:
        """Remove custom address and pin. No prompt."""
        self._remove_pin_fn(pin_id)
        self._custom_pins = [(pid, a, c, la, ln) for pid, a, c, la, ln in self._custom_pins if pid != pin_id]
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(MARKER_INDEX_ROLE) == pin_id:
                self._table.removeRow(row)
                break
        self._update_table_height()
        if self._table.rowCount() == 0:
            self._table.setVisible(False)
            if self._table_in_layout:
                self._table_in_layout = False
                self._main_layout.removeWidget(self._table)

    def _on_custom_table_selection_changed(self):
        """When user selects a custom row: notify parent to move to pin and clear main table."""
        if not self._on_custom_row_selected_fn:
            return
        rows = self._table.selectedItems()
        if not rows:
            return
        row = rows[0].row()
        item = self._table.item(row, 1)
        pin_id = item.data(MARKER_INDEX_ROLE) if item else None
        if pin_id is None:
            return
        coords = self.get_pin_coords(pin_id)
        if coords:
            lat, lng = coords
            self._on_custom_row_selected_fn(lat, lng, pin_id)

    def clear_all(self):
        """Remove all custom pins from map and clear table."""
        for pin_id, _, _, _, _ in self._custom_pins:
            self._remove_pin_fn(pin_id)
        self._custom_pins.clear()
        self._table.setRowCount(0)
        self._table.setVisible(False)
        if self._table_in_layout:
            self._table_in_layout = False
            self._main_layout.removeWidget(self._table)
        self._update_table_height()
        self._set_error_border(False)
        self._next_pin_id = CUSTOM_PIN_ID_BASE

    def _update_table_height(self):
        rc = self._table.rowCount()
        if rc == 0:
            self._table.setFixedHeight(0)
        else:
            self._table.resizeRowsToContents()
            h = self._table.horizontalHeader().height()
            for i in range(rc):
                h += self._table.rowHeight(i)
            self._table.setFixedHeight(min(h, 120))

    def get_next_pin_id(self) -> int:
        pid = self._next_pin_id
        self._next_pin_id += 1
        return pid


def _add_default_customer(df):
    """Prepend default customer (Kontor) to DataFrame."""
    import pandas as pd
    from utils import get_default_customer
    default = pd.DataFrame([get_default_customer()])
    return pd.concat([default, df], ignore_index=True)
