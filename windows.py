"""
Modular window classes for map views.
Each tool launches its own window; main dashboard remains responsive.
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QFrame,
    QCheckBox,
    QComboBox,
    QScrollArea,
    QGroupBox,
    QHeaderView,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QProgressBar,
)
from PySide6.QtWidgets import QColorDialog, QStyledItemDelegate, QStyleOptionViewItem
from PySide6.QtCore import Qt, QUrl, Signal, QTimer, QThread
from PySide6.QtGui import QFont, QColor, QBrush

from config import Styles, AppConfig

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
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


CUSTOM_PIN_ID_BASE = 100000


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


class CustomerListMapWindow(QMainWindow):
    """
    Window for displaying customer list on map.
    Customer list on left (sortable), map with colored pins on right.
    """

    def __init__(self, address_df, parent: QWidget | None = None, log_fn=None):
        super().__init__(parent)
        self.setWindowTitle("Customer List on Map")
        self.setMinimumSize(1000, 600)
        self.setAttribute(Qt.WA_DeleteOnClose)

        import pandas as pd
        base_df = address_df if address_df is not None and isinstance(address_df, pd.DataFrame) else pd.DataFrame()
        self._address_df = _add_default_customer(base_df)
        self._markers = []
        self._selection_blocked = False
        self._initial_pins_added = False  # guard: only zoom/select default once on first load
        self._log = log_fn or (lambda msg, lvl="info": print(msg))

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: Scrollable (Custom addresses + Customers table) ---
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(320)
        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        self._custom_addresses = CustomAddressesSection(
            add_pin_fn=self._add_custom_pin,
            remove_pin_fn=self._remove_custom_pin,
            log_fn=self._log,
        )
        self._custom_addresses.set_callbacks(self._on_custom_row_selected)
        left_layout.addWidget(QLabel("Custom addresses"))
        left_layout.addWidget(self._custom_addresses)
        left_layout.addWidget(QLabel("Customers"))
        self._table = QTableWidget()
        self._table.setItemDelegate(CustomerTableDelegate(self._table, self._table))
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        left_layout.addWidget(self._table)
        left_scroll.setWidget(left_content)
        splitter.addWidget(left_scroll)

        # --- Right: Map or error (stacked) ---
        from utils import config_disable_webengine_map
        use_webengine = HAS_WEBENGINE and not config_disable_webengine_map()
        self._map_stack = QStackedWidget()
        if use_webengine:
            self._map_view = QWebEngineView()
            self._map_view.setMinimumWidth(400)
            if MapPage:
                self._map_page = MapPage(self._map_view)
                self._map_view.setPage(self._map_page)
                self._map_page.pinClicked.connect(self._on_pin_clicked)
                self._map_page.renderProcessTerminated.connect(self._on_render_process_terminated)
            self._map_stack.addWidget(self._map_view)
        else:
            self._map_view = None
            self._map_page = None
            no_web = QFrame()
            no_web.setStyleSheet("background-color: #e5e5e5; border-radius: 8px;")
            no_web.setMinimumSize(400, 300)
            pl = QVBoxLayout(no_web)
            pl.addWidget(QLabel("Install pyside6-addons for map display:\npip install pyside6-addons"))
            self._map_stack.addWidget(no_web)

        self._map_error_widget = QWidget()
        err_layout = QVBoxLayout(self._map_error_widget)
        err_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._map_error_label = QLabel("")
        self._map_error_label.setWordWrap(True)
        self._map_error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        err_layout.addWidget(self._map_error_label)
        btn_retry = QPushButton("Retry")
        btn_retry.clicked.connect(self._on_map_retry)
        err_layout.addWidget(btn_retry, alignment=Qt.AlignmentFlag.AlignCenter)
        self._map_stack.addWidget(self._map_error_widget)
        splitter.addWidget(self._map_stack)

        splitter.setSizes([400, 600])
        layout.addWidget(splitter)

        self._log("Customer List Map: Geocoding addresses...", "info")
        self._populate_table()
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self._start_geocoding()

    def _populate_table(self) -> None:
        """Fill table from address DataFrame."""
        from utils import parse_color_for_marker, text_color_for_background, title_case_display

        df = self._address_df
        cols = AppConfig.ADDRESS_SOURCE_COLUMNS
        self._table.setSortingEnabled(False)
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.setRowCount(len(df))

        for i, row in df.iterrows():
            for j, col in enumerate(cols):
                val = row.get(col, "")
                if col in ("Förnamn", "Efternamn"):
                    val = title_case_display(str(val) if val else "")
                if col == "Färg":
                    color = parse_color_for_marker(val)
                    item = QTableWidgetItem(str(val) if val else "")
                    item.setData(Qt.ItemDataRole.UserRole, color)
                    item.setBackground(QBrush(QColor(color)))
                    item.setForeground(QBrush(QColor(text_color_for_background(color))))
                else:
                    item = QTableWidgetItem(str(val) if val else "")
                item.setData(MARKER_INDEX_ROLE, i)
                self._table.setItem(i, j, item)

        hh = self._table.horizontalHeader()
        if len(cols) >= 4:
            hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            hh.resizeSection(0, 50)
            hh.resizeSection(1, 90)
            hh.resizeSection(2, 90)
            hh.resizeSection(3, 220)
        else:
            for c in range(len(cols)):
                hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
        self._table.setSortingEnabled(True)

    def _on_render_process_terminated(self, status, exit_code: int) -> None:
        """WebEngine render process crashed - show fallback instead of crashing."""
        from PySide6.QtWebEngineCore import QWebEnginePage
        if status != QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            self._log("Map render process ended unexpectedly. Refresh the map if needed.", "warn")

    def _on_pin_clicked(self, marker_id: int) -> None:
        """Pin clicked: select row and zoom to pin. Zoom is done from Python so the map doesn't pan
        during the click (which could cause a spurious click on another pin, e.g. the default)."""
        # Custom pin clicked
        if marker_id >= CUSTOM_PIN_ID_BASE:
            self._selection_blocked = True
            if self._custom_addresses.select_row_by_pin_id(marker_id):
                coords = self._custom_addresses.get_pin_coords(marker_id)
                if coords and HAS_WEBENGINE and self._map_view:
                    lat, lng = coords
                    def _move():
                        if self._map_view and self._map_view.page():
                            self._map_view.page().runJavaScript(
                                f"moveToPin({lat}, {lng}); highlightPin({marker_id});"
                            )
                    QTimer.singleShot(50, _move)
                QTimer.singleShot(0, lambda: setattr(self, "_selection_blocked", False))
                return
            self._selection_blocked = False
            return

        # Customer pin clicked
        self._selection_blocked = True
        for row in range(self._table.rowCount()):
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None and item.data(MARKER_INDEX_ROLE) == marker_id:
                    self._custom_addresses.clear_selection()
                    self._table.selectRow(row)
                    self._table.scrollTo(self._table.model().index(row, 0))
                    # Move and highlight from Python, deferred, so map doesn't pan during the click
                    if self._markers and marker_id < len(self._markers) and HAS_WEBENGINE and self._map_view:
                        m = self._markers[marker_id]
                        lat, lng, mid = m["lat"], m["lng"], marker_id
                        def _move():
                            if self._map_view and self._map_view.page():
                                self._map_view.page().runJavaScript(f"moveToPin({lat}, {lng}); highlightPin({mid});")
                        QTimer.singleShot(50, _move)
                    QTimer.singleShot(0, lambda: setattr(self, "_selection_blocked", False))
                    return
        self._selection_blocked = False

    def _on_custom_row_selected(self, lat: float, lng: float, pin_id: int) -> None:
        """Called when user selects a custom address row: clear main table, move to pin."""
        self._selection_blocked = True
        self._table.clearSelection()
        if HAS_WEBENGINE and self._map_view and self._map_view.page():
            def _move():
                if self._map_view and self._map_view.page():
                    self._map_view.page().runJavaScript(
                        f"moveToPin({lat}, {lng}); highlightPin({pin_id});"
                    )
            QTimer.singleShot(50, _move)
        QTimer.singleShot(0, lambda: setattr(self, "_selection_blocked", False))

    def _on_table_selection_changed(self) -> None:
        """Table selection changed: clear custom selection, move to pin (no zoom change) and highlight."""
        if self._selection_blocked:
            return
        rows = self._table.selectedItems()
        if not rows:
            return
        self._custom_addresses.clear_selection()
        if not self._markers or not HAS_WEBENGINE or not self._map_view:
            return
        item = rows[0]
        marker_id = item.data(MARKER_INDEX_ROLE)
        if marker_id is None or marker_id >= len(self._markers):
            return
        m = self._markers[marker_id]
        self._map_view.page().runJavaScript(f"moveToPin({m['lat']}, {m['lng']}); highlightPin({marker_id});")

    def _add_custom_pin(self, address: str, color: str, lat: float, lng: float, pin_id: int) -> None:
        if not HAS_WEBENGINE or not self._map_view or not self._map_view.page():
            return
        import json
        name_esc = json.dumps(address[:30])
        color_esc = json.dumps(color)
        info_esc = json.dumps(f"<b>{address[:50]}</b>")
        try:
            self._map_view.page().runJavaScript(
                f"addPin({pin_id}, {lat}, {lng}, {name_esc}, {color_esc}, {info_esc}, '#FFFFFF', 0, 0);"
            )
        except Exception:
            pass

    def _remove_custom_pin(self, pin_id: int) -> None:
        if HAS_WEBENGINE and self._map_view and self._map_view.page():
            try:
                self._map_view.page().runJavaScript(f"removePin({pin_id});")
            except Exception:
                pass

    def closeEvent(self, event):
        self._log("Customer List on Map closed.", "info")
        self._custom_addresses.clear_all()
        super().closeEvent(event)

    def _show_map_error(self, message: str) -> None:
        """Show error page with message and Retry button."""
        self._map_error_label.setText(message)
        self._map_stack.setCurrentWidget(self._map_error_widget)

    def _on_map_retry(self) -> None:
        """Retry loading map."""
        self._map_stack.setCurrentIndex(0)
        self._start_geocoding()

    def _start_geocoding(self) -> None:
        """Geocode addresses and show map. Google Maps only; error + retry on failure."""
        from PySide6.QtCore import QThread
        from utils import (
            geocode_addresses,
            load_google_maps_api_key,
            start_map_server,
            get_map_url,
        )

        class GeocodeWorker(QThread):
            logMessage = Signal(str, str)

            def __init__(self, df, api_key="", log_fn=None):
                super().__init__()
                self.df = df
                self.api_key = api_key
                self._log_fn = log_fn
                self.result = []

            def run(self):
                def safe_log(msg, lvl="info"):
                    self.logMessage.emit(msg, lvl)
                try:
                    self.result = geocode_addresses(self.df, self.api_key, safe_log)
                except Exception as e:
                    self.logMessage.emit(f"Geocoding error: {e}", "error")
                    self.result = []

        api_key = load_google_maps_api_key()

        if not api_key:
            self._show_map_error(
                "Google Maps API key required.\n\n"
                "Set GOOGLE_MAPS_API_KEY env var or add google_maps_api_key to config.json"
            )
            self._log("No API key - set GOOGLE_MAPS_API_KEY or config.json", "error")
            return

        if not HAS_WEBENGINE or not self._map_view:
            self._show_map_error("Map module not available.\n\nInstall pyside6-addons for map display.")
            return

        if not start_map_server(api_key) or not get_map_url():
            self._show_map_error("Failed to start map server.")
            return

        try:
            self._map_view.setUrl(QUrl(get_map_url()))
            self._map_view.page().loadFinished.connect(self._on_map_load_finished)
        except Exception as e:
            self._show_map_error(f"Map load failed:\n\n{str(e)}")
            self._log(f"Map load failed: {e}", "error")

    def _on_map_load_finished(self) -> None:
        """Start geocoding after map loads; pins added when geocoding done."""
        page = self._map_view.page() if self._map_view else None
        if page:
            try:
                page.loadFinished.disconnect(self._on_map_load_finished)
            except Exception:
                pass
        from PySide6.QtCore import QThread
        from utils import geocode_addresses, load_google_maps_api_key

        class GeocodeWorker(QThread):
            logMessage = Signal(str, str)

            def __init__(self, df, api_key="", log_fn=None):
                super().__init__()
                self.df = df
                self.api_key = api_key
                self.result = []

            def run(self):
                def safe_log(msg, lvl="info"):
                    self.logMessage.emit(msg, lvl)
                self.result = geocode_addresses(self.df, self.api_key, safe_log)

        api_key = load_google_maps_api_key()
        self._worker = GeocodeWorker(self._address_df, api_key, self._log)
        self._worker.logMessage.connect(self._log, Qt.ConnectionType.QueuedConnection)
        self._worker.finished.connect(self._on_geocoding_done_google)
        self._worker.start()

    def _on_geocoding_done_google(self) -> None:
        """Add pins to Google Maps via runJavaScript."""
        from utils import get_map_url
        import json

        from utils import apply_offset_for_overlapping_pins
        self._markers = apply_offset_for_overlapping_pins(self._worker.result)
        if not HAS_WEBENGINE or not self._map_view or not get_map_url():
            self._log("Customer List Map: Map not available.", "error")
            return

        if not self._markers:
            self._log("Customer List Map: No pins - geocoding failed for all addresses.", "error")
            return

        self._log(f"Customer List Map: Adding {len(self._markers)} pins...", "info")

        def _html_esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        def add_pins():
            from utils import title_case_display
            for i, m in enumerate(self._markers):
                label_display = title_case_display(m.get("label", ""))
                name_esc = json.dumps(label_display)
                color = m.get("color", "#FFFFFF")
                color_esc = json.dumps(color)
                text_color_esc = json.dumps("#FFFFFF")
                lox = m.get("label_offset_x", 0)
                loy = m.get("label_offset_y", 0)
                info = f"<b>{_html_esc(label_display)}</b><br>{_html_esc(m.get('address', ''))}"
                info_esc = json.dumps(info)
                script = f"addPin({i}, {m['lat']}, {m['lng']}, {name_esc}, {color_esc}, {info_esc}, {text_color_esc}, {lox}, {loy});"
                self._map_view.page().runJavaScript(script)
            self._log(f"Customer List Map: {len(self._markers)} pins on map.", "success")
            if self._markers and not self._initial_pins_added:
                self._initial_pins_added = True
                m0 = self._markers[0]
                self._map_view.page().runJavaScript(f"flyToPin({m0['lat']}, {m0['lng']}); highlightPin(0);")
                self._selection_blocked = True
                if self._table.rowCount() > 0:
                    self._table.selectRow(0)
                self._selection_blocked = False

        def check_ready(result):
            if result and self._markers:
                add_pins()
            else:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(200, lambda: self._map_view.page().runJavaScript("window.mapReady", check_ready))

        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, lambda: self._map_view.page().runJavaScript("window.mapReady", check_ready))

# =============================================================================
# Rule Editor Window
# =============================================================================


def _rule_to_display(rule: dict) -> str:
    """Format rule for display in list."""
    rtype = rule.get("type", "")
    col = rule.get("column", "")
    if rtype == "fill_default_address":
        prefs = rule.get("prefixes", [])
        prefs_str = ", ".join(prefs) if isinstance(prefs, list) else str(prefs)
        return f"Fill address when {col} starts with: {prefs_str}"
    if rtype == "remove_empty":
        return f"Remove when {col} is empty"
    if rtype == "remove_starts_with":
        pat = rule.get("pattern", "")
        return f"Remove when {col} starts with: {pat}"
    return f"{rtype}: {col}"


class RuleEditorWindow(QMainWindow):
    """Window to edit route data rules (fill address, remove rows)."""

    def __init__(self, parent: QWidget | None = None, log_fn=None):
        super().__init__(parent)
        self.setWindowTitle("Route Rules Editor")
        self._log = log_fn or (lambda msg, lvl="info": None)
        self.setMinimumSize(500, 400)
        self.setAttribute(Qt.WA_DeleteOnClose)

        from utils import get_route_rules, save_route_rules, DEFAULT_ROUTE_RULES

        self._get_rules = get_route_rules
        self._save_rules = save_route_rules
        self._default_rules = DEFAULT_ROUTE_RULES
        self._rules = list(self._get_rules())

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addWidget(QLabel("Rules are applied in order when loading route data:"))
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Rule", "Details"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._on_add)
        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._on_edit)
        btn_remove = QPushButton("Remove")
        btn_remove.clicked.connect(self._on_remove)
        btn_up = QPushButton("Move up")
        btn_up.clicked.connect(self._on_move_up)
        btn_down = QPushButton("Move down")
        btn_down.clicked.connect(self._on_move_down)
        btn_reset = QPushButton("Reset to default")
        btn_reset.clicked.connect(self._on_reset)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_up)
        btn_row.addWidget(btn_down)
        btn_row.addStretch()
        btn_row.addWidget(btn_reset)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        self._refresh_table()

    def _refresh_table(self) -> None:
        self._table.setRowCount(len(self._rules))
        for i, r in enumerate(self._rules):
            rtype = r.get("type", "")
            self._table.setItem(i, 0, QTableWidgetItem(rtype))
            self._table.setItem(i, 1, QTableWidgetItem(_rule_to_display(r)))

    def _edit_rule_dialog(self, rule: dict | None = None) -> dict | None:
        """Show edit dialog, return rule dict or None if cancelled."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Rule" if rule else "Add Rule")
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("Type:"))
        type_combo = QComboBox()
        type_combo.addItems(["fill_default_address", "remove_empty", "remove_starts_with"])
        if rule:
            idx = type_combo.findText(rule.get("type", ""))
            if idx >= 0:
                type_combo.setCurrentIndex(idx)
        layout.addWidget(type_combo)

        layout.addWidget(QLabel("Column:"))
        col_edit = QLineEdit()
        col_edit.setPlaceholderText("e.g. Besökstyp, Adress, Slinga, Sign.")
        if rule:
            col_edit.setText(rule.get("column", ""))
        layout.addWidget(col_edit)

        layout.addWidget(QLabel("Pattern (for remove_starts_with):"))
        pattern_edit = QLineEdit()
        pattern_edit.setPlaceholderText("e.g. xExterna, AVBOK, SJUKHUS")
        if rule and rule.get("type") == "remove_starts_with":
            pattern_edit.setText(rule.get("pattern", ""))
        layout.addWidget(pattern_edit)

        layout.addWidget(QLabel("Prefixes (for fill_default_address, comma-separated):"))
        prefs_edit = QLineEdit()
        prefs_edit.setPlaceholderText("e.g. AVSLUT, UPPSTART, RAST")
        if rule and rule.get("type") == "fill_default_address":
            prefs = rule.get("prefixes", [])
            prefs_edit.setText(", ".join(prefs) if isinstance(prefs, list) else str(prefs))
        layout.addWidget(prefs_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        rtype = type_combo.currentText().strip()
        col = col_edit.text().strip()
        result = {"type": rtype, "column": col}
        if rtype == "remove_starts_with":
            result["pattern"] = pattern_edit.text().strip()
        elif rtype == "fill_default_address":
            parts = [p.strip() for p in prefs_edit.text().split(",") if p.strip()]
            result["prefixes"] = parts
        return result

    def _on_add(self) -> None:
        r = self._edit_rule_dialog()
        if r:
            self._rules.append(r)
            self._refresh_table()

    def _on_edit(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        r = self._edit_rule_dialog(self._rules[row])
        if r:
            self._rules[row] = r
            self._refresh_table()

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._rules.pop(row)
            self._refresh_table()

    def _on_move_up(self) -> None:
        row = self._table.currentRow()
        if row > 0:
            self._rules[row], self._rules[row - 1] = self._rules[row - 1], self._rules[row]
            self._refresh_table()
            self._table.selectRow(row - 1)

    def _on_move_down(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._rules) - 1:
            self._rules[row], self._rules[row + 1] = self._rules[row + 1], self._rules[row]
            self._refresh_table()
            self._table.selectRow(row + 1)

    def _on_reset(self) -> None:
        if QMessageBox.question(
            self, "Reset", "Reset all rules to default?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self._rules = list(self._default_rules)
            self._refresh_table()

    def _on_save(self) -> None:
        self._save_rules(self._rules)
        QMessageBox.information(self, "Saved", "Rules saved. They will apply when loading route data.")
        self._log("Route rules saved.", "success")
        self.close()

    def closeEvent(self, event):
        self._log("Route Rules Editor closed.", "info")
        super().closeEvent(event)


class RoutesMapWindow(QMainWindow):
    """
    Window for displaying routes on map.
    Left: routes list with visits (time, address). Each route has checkbox to toggle.
    Right: map with pins and arrows between consecutive visits.
    Date selector when data spans multiple days.
    """

    def __init__(self, route_df, parent: QWidget | None = None, log_fn=None):
        super().__init__(parent)
        self.setWindowTitle("Routes on Map")
        self.setMinimumSize(1200, 700)
        self.setAttribute(Qt.WA_DeleteOnClose)

        import pandas as pd
        self._route_df = route_df if route_df is not None and isinstance(route_df, pd.DataFrame) else pd.DataFrame()
        self._log = log_fn or (lambda msg, lvl="info": print(msg))
        self._markers_by_trip = {}  # trip_key -> [marker_ids]
        self._polylines_by_trip = {}  # trip_key -> polyline_id
        self._all_markers = []  # flat list of {lat, lng, label, address, route_key, visit_idx}
        self._use_google_map = False

        from utils import (
            build_routes_by_date,
            get_default_route_address,
            split_route_into_trips,
        )
        default_addr = get_default_route_address()
        self._default_address = default_addr
        self._routes_by_date = build_routes_by_date(self._route_df, default_addr)
        self._routes_by_date_trips = {}  # {date: {slinga: [trip_visits, ...]}}
        for date_str, routes in self._routes_by_date.items():
            self._routes_by_date_trips[date_str] = {}
            for slinga, visits in routes.items():
                self._routes_by_date_trips[date_str][slinga] = split_route_into_trips(visits, default_addr)
        self._dates = sorted(self._routes_by_date.keys())
        self._current_date = self._dates[0] if self._dates else None
        self._trip_visibility = {}  # trip_key -> bool
        self._visit_to_marker = {}  # (date, slinga, trip_idx, visit_idx) -> marker_id
        self._marker_to_visit = {}  # marker_id -> (date, slinga, trip_idx, visit_idx)
        self._trip_tables = {}  # trip_key -> QTableWidget
        self._route_sections = {}  # slinga -> CollapsibleSection
        self._trip_sections = {}  # trip_key -> CollapsibleSection
        self._route_selection_blocked = False  # block zoom when selecting from pin click
        self._initial_pins_added = False  # guard: only zoom to default once on first load

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: Scrollable (Custom addresses + Routes list) ---
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setMinimumWidth(320)
        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)

        self._custom_addresses = CustomAddressesSection(
            add_pin_fn=self._add_custom_pin,
            remove_pin_fn=self._remove_custom_pin,
            log_fn=self._log,
        )
        self._custom_addresses.set_callbacks(self._on_custom_row_selected)
        left_layout.addWidget(QLabel("Custom addresses"))
        left_layout.addWidget(self._custom_addresses)

        left_layout.addWidget(QLabel("Routes"))
        routes_container = QFrame()
        routes_container.setObjectName("routesSection")
        routes_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        routes_container.setStyleSheet(
            "QFrame#routesSection { background-color: #ffffff; border: 1px solid #edebe9; border-radius: 8px; }"
        )
        routes_container_layout = QVBoxLayout(routes_container)
        routes_container_layout.setContentsMargins(6, 4, 6, 4)
        routes_container_layout.setSpacing(4)

        if len(self._dates) > 1:
            date_row = QHBoxLayout()
            date_row.addWidget(QLabel("Date:"))
            self._date_combo = QComboBox()
            for d in self._dates:
                self._date_combo.addItem(d, d)
            self._date_combo.currentIndexChanged.connect(self._on_date_changed)
            date_row.addWidget(self._date_combo)
            routes_container_layout.addLayout(date_row)

        _btn_grey = "QPushButton#secondary { font-size: 9pt; padding: 2px 6px; min-width: 0; }"
        sel_row = QHBoxLayout()
        btn_select_all = QPushButton("Select all")
        btn_select_all.setObjectName("secondary")
        btn_select_all.setFlat(True)
        btn_select_all.setStyleSheet(_btn_grey)
        btn_select_all.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_select_all.setFixedWidth(btn_select_all.fontMetrics().horizontalAdvance("Select all") + 14)
        btn_select_all.clicked.connect(self._on_select_all)
        btn_deselect_all = QPushButton("Deselect all")
        btn_deselect_all.setObjectName("secondary")
        btn_deselect_all.setFlat(True)
        btn_deselect_all.setStyleSheet(_btn_grey)
        btn_deselect_all.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_deselect_all.setFixedWidth(btn_deselect_all.fontMetrics().horizontalAdvance("Deselect all") + 14)
        btn_deselect_all.clicked.connect(self._on_deselect_all)
        btn_expand_all = QPushButton("Expand all")
        btn_expand_all.setObjectName("secondary")
        btn_expand_all.setFlat(True)
        btn_expand_all.setStyleSheet(_btn_grey)
        btn_expand_all.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_expand_all.setFixedWidth(btn_expand_all.fontMetrics().horizontalAdvance("Expand all") + 14)
        btn_expand_all.clicked.connect(self._on_expand_all)
        btn_collapse_all = QPushButton("Collapse all")
        btn_collapse_all.setObjectName("secondary")
        btn_collapse_all.setFlat(True)
        btn_collapse_all.setStyleSheet(_btn_grey)
        btn_collapse_all.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_collapse_all.setFixedWidth(btn_collapse_all.fontMetrics().horizontalAdvance("Collapse all") + 14)
        btn_collapse_all.clicked.connect(self._on_collapse_all)
        sel_row.addWidget(btn_select_all)
        sel_row.addWidget(btn_deselect_all)
        sel_row.addWidget(btn_expand_all)
        sel_row.addWidget(btn_collapse_all)
        sel_row.addSpacing(12)
        sel_row.addWidget(QLabel("Sort:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("By name", "name")
        self._sort_combo.addItem("By start time", "time")
        self._sort_combo.setStyleSheet("font-size: 9pt; min-width: 100px;")
        from utils import get_route_sort_order
        sort_order = get_route_sort_order()
        idx = self._sort_combo.findData(sort_order)
        if idx >= 0:
            self._sort_combo.blockSignals(True)
            self._sort_combo.setCurrentIndex(idx)
            self._sort_combo.blockSignals(False)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sel_row.addWidget(self._sort_combo)
        sel_row.addStretch()
        routes_container_layout.addLayout(sel_row)

        self._trip_buttons_widget = QWidget()
        self._trip_buttons_layout = QHBoxLayout(self._trip_buttons_widget)
        self._trip_buttons_layout.setContentsMargins(0, 4, 0, 4)
        routes_container_layout.addWidget(self._trip_buttons_widget)

        routes_widget = QWidget()
        self._routes_scroll_layout = QVBoxLayout(routes_widget)
        routes_container_layout.addWidget(routes_widget, 1)

        left_layout.addWidget(routes_container)
        self._left_scroll.setWidget(left_content)
        splitter.addWidget(self._left_scroll)

        # --- Right: Map or error (stacked) ---
        from utils import config_disable_webengine_map
        use_webengine = HAS_WEBENGINE and not config_disable_webengine_map()
        self._map_stack = QStackedWidget()
        if use_webengine:
            self._map_view = QWebEngineView()
            self._map_view.setMinimumWidth(500)
            if MapPage:
                self._map_page = MapPage(self._map_view)
                self._map_view.setPage(self._map_page)
                self._map_page.pinClicked.connect(self._on_pin_clicked)
                self._map_page.renderProcessTerminated.connect(self._on_render_process_terminated)
            else:
                self._map_page = None
            self._map_stack.addWidget(self._map_view)
        else:
            self._map_view = None
            pl = QFrame()
            pl.setStyleSheet("background-color: #e5e5e5; border-radius: 8px;")
            pl.setMinimumSize(500, 400)
            pl_layout = QVBoxLayout(pl)
            pl_layout.addWidget(QLabel("Install pyside6-addons for map display"))
            self._map_stack.addWidget(pl)

        self._map_error_widget = QWidget()
        err_layout = QVBoxLayout(self._map_error_widget)
        err_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._map_error_label = QLabel("")
        self._map_error_label.setWordWrap(True)
        self._map_error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        err_layout.addWidget(self._map_error_label)
        btn_retry = QPushButton("Retry")
        btn_retry.clicked.connect(self._on_map_retry)
        err_layout.addWidget(btn_retry, alignment=Qt.AlignmentFlag.AlignCenter)
        self._map_stack.addWidget(self._map_error_widget)
        splitter.addWidget(self._map_stack)

        splitter.setSizes([420, 780])
        layout.addWidget(splitter)

        self._populate_routes_list()
        if self._route_df.empty or not self._routes_by_date:
            self._log("No route data to display.", "warn")
        else:
            self._log("Routes Map: Geocoding addresses...", "info")
            self._start_geocoding()

    def _trip_key(self, date_str: str, slinga: str, trip_idx: int) -> str:
        return f"{date_str}|{slinga}|{trip_idx}"

    def _get_trip_name_for_key(self, trip_key: str) -> str | None:
        """Get trip name (morning/afternoon/evening) for a trip_key."""
        parts = trip_key.split("|")
        if len(parts) != 3:
            return None
        date_str, slinga, idx_str = parts
        if not idx_str.isdigit():
            return None
        trip_idx = int(idx_str)
        trips = self._routes_by_date_trips.get(date_str, {}).get(slinga, [])
        if trip_idx >= len(trips):
            return None
        trip_item = trips[trip_idx]
        if isinstance(trip_item, tuple) and len(trip_item) == 2:
            return trip_item[0]
        return None

    def _populate_routes_list(self) -> None:
        """Fill left panel with route groups, trips, and visit tables."""
        self._trip_tables.clear()
        self._route_sections.clear()
        self._trip_sections.clear()
        while self._routes_scroll_layout.count():
            item = self._routes_scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._current_date or self._current_date not in self._routes_by_date_trips:
            self._routes_scroll_layout.addWidget(QLabel("No routes for selected date."))
            return

        routes_trips = self._routes_by_date_trips[self._current_date]
        route_names = list(routes_trips.keys())
        from utils import get_route_colors, sort_routes_for_display, _get_trip_visits
        route_colors = get_route_colors(route_names)
        for slinga, trips in sort_routes_for_display(routes_trips):
            color = route_colors.get(slinga, "#777777")
            route_section = CollapsibleSection(slinga, initial_expanded=False, header_color=color)
            self._route_sections[slinga] = route_section
            group_layout = route_section.content_layout()
            for trip_idx, trip_item in enumerate(trips):
                trip_name, trip_visits = (trip_item[0], trip_item[1]) if isinstance(trip_item, tuple) else (f"Trip {trip_idx + 1}", trip_item)
                tk = self._trip_key(self._current_date, slinga, trip_idx)
                visible = self._trip_visibility.get(tk, True)
                self._trip_visibility[tk] = visible

                trip_label = trip_name if len(trips) > 1 else "Show on map"
                cb = QCheckBox("Show on map")
                cb.setChecked(visible)
                cb.stateChanged.connect(lambda s, k=tk: self._on_trip_toggle(k, s == 2))
                trip_section = CollapsibleSection(trip_label, header_widgets=[cb], initial_expanded=False)
                self._trip_sections[tk] = trip_section
                trip_layout = trip_section.content_layout()

                table = QTableWidget()
                table.setColumnCount(3)
                table.setHorizontalHeaderLabels(["Time", "Address", "Name"])
                table.setAlternatingRowColors(True)
                table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                hh = table.horizontalHeader()
                hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
                hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
                hh.resizeSection(0, 55)
                hh.resizeSection(1, 180)
                hh.resizeSection(2, 100)
                table.setRowCount(len(trip_visits))
                table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
                for row, v in enumerate(trip_visits):
                    start = v.get("starttid")
                    time_str = ""
                    if hasattr(start, "strftime"):
                        time_str = start.strftime("%H:%M")
                    else:
                        try:
                            import pandas as pd
                            dt = pd.to_datetime(start)
                            time_str = dt.strftime("%H:%M")
                        except Exception:
                            time_str = str(start)[:5]
                    ti0 = QTableWidgetItem(time_str)
                    ti0.setData(VISIT_ROLE, (slinga, trip_idx, row))
                    table.setItem(row, 0, ti0)
                    table.setItem(row, 1, QTableWidgetItem(str(v.get("adress", ""))))
                    table.setItem(row, 2, QTableWidgetItem(str(v.get("namn", ""))))
                table.setSizeAdjustPolicy(QTableWidget.SizeAdjustPolicy.AdjustToContents)
                table.resizeRowsToContents()
                table.verticalHeader().setVisible(False)
                table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                h = table.horizontalHeader().height()
                for i in range(table.rowCount()):
                    h += table.rowHeight(i)
                table.setMinimumHeight(h)
                table.setMaximumHeight(h)
                self._trip_tables[tk] = table
                table.itemSelectionChanged.connect(self._on_route_table_selection_changed)
                trip_layout.addWidget(table)
                group_layout.addWidget(trip_section)
            self._routes_scroll_layout.addWidget(route_section)

        self._populate_trip_buttons()

    def _populate_trip_buttons(self) -> None:
        """Build Morning, Afternoon, Evening On/Off buttons."""
        from utils import TRIP_NAMES

        while self._trip_buttons_layout.count():
            item = self._trip_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._current_date or self._current_date not in self._routes_by_date_trips:
            return

        _btn_style = (
            "QPushButton#secondary { background-color: #edebe9; color: #323130; font-size: 8pt; padding: 2px 4px; min-width: 0; } "
            "QPushButton#secondary:hover { background-color: #d2d0ce; color: #323130; }"
        )
        for trip_name in TRIP_NAMES:
            lbl = QLabel(f"{trip_name.capitalize()}:")
            lbl.setStyleSheet("font-size: 8pt;")
            self._trip_buttons_layout.addWidget(lbl)
            btn_sel = QPushButton("On")
            btn_sel.setObjectName("secondary")
            btn_sel.setFlat(True)
            btn_sel.setStyleSheet(_btn_style)
            btn_sel.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn_sel.clicked.connect(lambda checked, name=trip_name: self._on_select_trip_by_name(name))
            btn_desel = QPushButton("Off")
            btn_desel.setObjectName("secondary")
            btn_desel.setFlat(True)
            btn_desel.setStyleSheet(_btn_style)
            btn_desel.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn_desel.clicked.connect(lambda checked, name=trip_name: self._on_deselect_trip_by_name(name))
            self._trip_buttons_layout.addWidget(btn_sel)
            self._trip_buttons_layout.addWidget(btn_desel)
        self._trip_buttons_layout.addStretch()

    def _on_select_trip_by_name(self, trip_name: str) -> None:
        """Turn on all trips with given name (morning/afternoon/evening) across all routes."""
        for tk in self._trip_visibility:
            if self._get_trip_name_for_key(tk) == trip_name:
                self._trip_visibility[tk] = True
        self._refresh_trip_checkboxes()
        self._update_map_visibility()

    def _on_deselect_trip_by_name(self, trip_name: str) -> None:
        """Turn off all trips with given name (morning/afternoon/evening) across all routes."""
        for tk in self._trip_visibility:
            if self._get_trip_name_for_key(tk) == trip_name:
                self._trip_visibility[tk] = False
        self._refresh_trip_checkboxes()
        self._update_map_visibility()

    def _on_date_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._dates):
            self._current_date = self._dates[idx]
            self._populate_routes_list()
            self._update_map_visibility()

    def _on_sort_changed(self, idx: int) -> None:
        """Change route sort order and refresh the list."""
        order = self._sort_combo.currentData()
        if order:
            from utils import save_route_sort_order
            save_route_sort_order(order)
            self._populate_routes_list()

    def _on_trip_toggle(self, trip_key: str, visible: bool) -> None:
        self._trip_visibility[trip_key] = visible
        self._update_map_visibility()

    def _add_custom_pin(self, address: str, color: str, lat: float, lng: float, pin_id: int) -> None:
        if not HAS_WEBENGINE or not self._map_view or not self._map_view.page():
            return
        import json
        name_esc = json.dumps(address[:30])
        color_esc = json.dumps(color)
        info_esc = json.dumps(f"<b>{address[:50]}</b>")
        try:
            self._map_view.page().runJavaScript(
                f"addPin({pin_id}, {lat}, {lng}, {name_esc}, {color_esc}, {info_esc}, '#FFFFFF', 0, 0);"
            )
        except Exception:
            pass

    def _remove_custom_pin(self, pin_id: int) -> None:
        if HAS_WEBENGINE and self._map_view and self._map_view.page():
            try:
                self._map_view.page().runJavaScript(f"removePin({pin_id});")
            except Exception:
                pass

    def closeEvent(self, event):
        self._log("Routes on Map closed.", "info")
        self._custom_addresses.clear_all()
        super().closeEvent(event)

    def _on_render_process_terminated(self, status, exit_code: int) -> None:
        """WebEngine render process crashed."""
        from PySide6.QtWebEngineCore import QWebEnginePage
        if status != QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            self._log("Map render process ended unexpectedly. Refresh the map if needed.", "warn")

    def _on_pin_clicked(self, marker_id: int) -> None:
        """Pin clicked: expand route/trip, select the corresponding visit row, move and highlight.
        From Python, deferred, so map doesn't pan during the click (like customer map)."""
        # Custom pin clicked
        if marker_id >= CUSTOM_PIN_ID_BASE:
            self._route_selection_blocked = True
            if self._custom_addresses.select_row_by_pin_id(marker_id):
                coords = self._custom_addresses.get_pin_coords(marker_id)
                if coords and HAS_WEBENGINE and self._map_view:
                    lat, lng = coords
                    def _move():
                        if self._map_view and self._map_view.page():
                            self._map_view.page().runJavaScript(
                                f"moveToPin({lat}, {lng}); highlightPin({marker_id});"
                            )
                    QTimer.singleShot(50, _move)
                self._clear_all_route_selections()
            QTimer.singleShot(0, lambda: setattr(self, "_route_selection_blocked", False))
            return

        visit_key = self._marker_to_visit.get(marker_id)
        if not visit_key:
            return
        date_str, slinga, trip_idx, visit_idx = visit_key
        if date_str != self._current_date:
            return
        trip_key = self._trip_key(date_str, slinga, trip_idx)
        table = self._trip_tables.get(trip_key)
        if not table or visit_idx >= table.rowCount():
            return
        route_section = self._route_sections.get(slinga)
        trip_section = self._trip_sections.get(trip_key)
        if route_section:
            route_section.set_expanded(True)
        if trip_section:
            trip_section.set_expanded(True)
        if trip_section:
            QTimer.singleShot(10, lambda: self._left_scroll.ensureWidgetVisible(trip_section))
        self._route_selection_blocked = True
        self._custom_addresses.clear_selection()
        table.selectRow(visit_idx)
        table.scrollTo(table.model().index(visit_idx, 0))
        m = next((x for x in self._all_markers if x.get("id") == marker_id), None)
        if m and HAS_WEBENGINE and self._map_view:
            lat, lng, mid = m["lat"], m["lng"], marker_id
            def _move():
                if self._map_view and self._map_view.page():
                    self._map_view.page().runJavaScript(f"moveToPin({lat}, {lng}); highlightPin({mid});")
            QTimer.singleShot(50, _move)
        QTimer.singleShot(0, lambda: setattr(self, "_route_selection_blocked", False))

    def _clear_all_route_selections(self) -> None:
        """Clear selection in all trip tables."""
        for table in self._trip_tables.values():
            table.clearSelection()

    def _on_custom_row_selected(self, lat: float, lng: float, pin_id: int) -> None:
        """Called when user selects a custom address row: clear route selections, move to pin."""
        self._route_selection_blocked = True
        self._clear_all_route_selections()
        if HAS_WEBENGINE and self._map_view and self._map_view.page():
            def _move():
                if self._map_view and self._map_view.page():
                    self._map_view.page().runJavaScript(
                        f"moveToPin({lat}, {lng}); highlightPin({pin_id});"
                    )
            QTimer.singleShot(50, _move)
        QTimer.singleShot(0, lambda: setattr(self, "_route_selection_blocked", False))

    def _on_route_table_selection_changed(self) -> None:
        """Visit row selected: clear custom selection, zoom to that pin if trip is visible."""
        if self._route_selection_blocked:
            return
        self._custom_addresses.clear_selection()
        if not HAS_WEBENGINE or not self._map_view or not self._map_view.page():
            return
        sender = self.sender()
        if not isinstance(sender, QTableWidget):
            return
        items = sender.selectedItems()
        if not items:
            return
        row = sender.row(items[0])
        item = sender.item(row, 0)
        if not item:
            return
        visit_data = item.data(VISIT_ROLE)
        if not visit_data or len(visit_data) != 3:
            return
        slinga, trip_idx, visit_idx = visit_data
        trip_key = self._trip_key(self._current_date, slinga, trip_idx)
        if not self._trip_visibility.get(trip_key, True):
            return
        marker_id = self._visit_to_marker.get((self._current_date, slinga, trip_idx, visit_idx))
        if marker_id is None:
            return
        m = next((x for x in self._all_markers if x.get("id") == marker_id), None)
        if not m:
            return
        self._map_view.page().runJavaScript(
            f"moveToPin({m['lat']}, {m['lng']}); highlightPin({marker_id});"
        )

    def _on_select_all(self) -> None:
        for k in self._trip_visibility:
            self._trip_visibility[k] = True
        self._refresh_trip_checkboxes()
        self._update_map_visibility()

    def _on_deselect_all(self) -> None:
        for k in self._trip_visibility:
            self._trip_visibility[k] = False
        self._refresh_trip_checkboxes()
        self._update_map_visibility()

    def _on_expand_all(self) -> None:
        """Expand all route and trip sections."""
        for section in self._route_sections.values():
            section.set_expanded(True)
        for section in self._trip_sections.values():
            section.set_expanded(True)

    def _on_collapse_all(self) -> None:
        """Collapse all route and trip sections."""
        for section in self._route_sections.values():
            section.set_expanded(False)
        for section in self._trip_sections.values():
            section.set_expanded(False)

    def _refresh_trip_checkboxes(self) -> None:
        """Recreate route list to sync checkboxes with _trip_visibility."""
        self._populate_routes_list()

    def _update_map_visibility(self) -> None:
        """Show/hide pins and polylines based on trip checkboxes."""
        if not HAS_WEBENGINE or not self._map_view or not self._map_view.page():
            return
        for tk, mid_list in self._markers_by_trip.items():
            vis = self._trip_visibility.get(tk, True)
            for mid in mid_list:
                self._map_view.page().runJavaScript(f"setPinVisible({mid}, {str(vis).lower()});")
        for tk, pid in self._polylines_by_trip.items():
            vis = self._trip_visibility.get(tk, True)
            self._map_view.page().runJavaScript(f"setPolylineVisible({pid}, {str(vis).lower()});")

    def _show_map_error(self, message: str) -> None:
        """Show error page with message and Retry button."""
        self._map_error_label.setText(message)
        self._map_stack.setCurrentWidget(self._map_error_widget)

    def _on_map_retry(self) -> None:
        """Retry loading map."""
        self._map_stack.setCurrentIndex(0)
        self._start_geocoding()

    def _start_geocoding(self) -> None:
        """Geocode unique addresses and update map. Google Maps only; error + retry on failure."""
        from utils import (
            load_google_maps_api_key,
            start_map_server,
            get_map_url,
        )

        from utils import _get_trip_visits
        addresses = []
        self._visit_address_map = []  # [(date, slinga, trip_idx, visit_idx_in_trip, address)]
        for date_str, routes in self._routes_by_date_trips.items():
            for slinga, trips in routes.items():
                for trip_idx, trip_item in enumerate(trips):
                    trip_visits = _get_trip_visits(trip_item)
                    for i, v in enumerate(trip_visits):
                        addr = (v.get("adress") or "").strip()
                        if addr:
                            addresses.append(addr)
                            self._visit_address_map.append((date_str, slinga, trip_idx, i, addr))

        unique_addrs = list(dict.fromkeys(a for a in addresses if a))
        default_addr = self._default_address
        if default_addr and default_addr not in unique_addrs:
            unique_addrs = [default_addr] + unique_addrs
        if not unique_addrs:
            self._log("No addresses to geocode.", "warn")
            return

        api_key = load_google_maps_api_key()

        if not api_key:
            self._show_map_error(
                "Google Maps API key required.\n\n"
                "Set GOOGLE_MAPS_API_KEY env var or add google_maps_api_key to config.json"
            )
            return

        if not HAS_WEBENGINE or not self._map_view:
            self._show_map_error("Map module not available.\n\nInstall pyside6-addons for map display.")
            return

        if not start_map_server(api_key) or not get_map_url():
            self._show_map_error("Failed to start map server.")
            return

        self._use_google_map = True
        try:
            self._map_view.setUrl(QUrl(get_map_url()))
            self._map_view.page().loadFinished.connect(
                lambda: self._run_geocode_and_update(api_key, unique_addrs)
            )
        except Exception as e:
            self._show_map_error(f"Map load failed:\n\n{str(e)}")
            self._log(f"Map load failed: {e}", "error")

    def _run_geocode_and_update(self, api_key: str, unique_addrs: list) -> None:
        from PySide6.QtCore import QThread
        from utils import geocode_route_addresses

        class GeocodeWorker(QThread):
            def __init__(self, addrs, api_key, log_fn):
                super().__init__()
                self.addrs = addrs
                self.api_key = api_key
                self._log = log_fn
                self.result = []

            def run(self):
                self.result = geocode_route_addresses(self.addrs, self.api_key, self._log)

        self._worker = GeocodeWorker(unique_addrs, api_key, self._log)
        self._worker.finished.connect(self._on_geocoding_done)
        self._worker.start()

    def _on_geocoding_done(self) -> None:
        from utils import get_map_url
        import json

        try:
            result = self._worker.result
        except Exception:
            result = []

        addr_to_coords = {r["address"]: (r["lat"], r["lng"]) for r in result}

        self._visit_to_marker.clear()
        self._marker_to_visit.clear()
        self._all_markers = []
        marker_id = 0
        for date_str, slinga, trip_idx, visit_idx, addr in self._visit_address_map:
            if addr not in addr_to_coords:
                continue
            lat, lng = addr_to_coords[addr]
            trips = self._routes_by_date_trips.get(date_str, {}).get(slinga, [])
            trip_item = trips[trip_idx] if trip_idx < len(trips) else None
            from utils import _get_trip_visits
            trip_visits = _get_trip_visits(trip_item) if trip_item else []
            visit = trip_visits[visit_idx] if visit_idx < len(trip_visits) else {}
            raw_namn = visit.get("namn", addr[:30])
            s = str(raw_namn).strip().lower() if raw_namn is not None else ""
            label = "" if (not s or s in ("nan", "none")) else str(raw_namn).strip()
            if not label:
                from utils import get_default_location_name
                label = get_default_location_name() if addr == self._default_address else addr[:30]
            self._all_markers.append({
                "id": marker_id,
                "lat": lat, "lng": lng, "label": label, "address": addr,
                "trip_key": self._trip_key(date_str, slinga, trip_idx), "visit_idx": visit_idx,
            })
            self._visit_to_marker[(date_str, slinga, trip_idx, visit_idx)] = marker_id
            self._marker_to_visit[marker_id] = (date_str, slinga, trip_idx, visit_idx)
            marker_id += 1

        if not self._use_google_map:
            self._show_map_error("Map configuration error. Please retry.")
            return

        if not HAS_WEBENGINE or not self._map_view:
            return
        if not get_map_url():
            return

        self._log(f"Routes Map: Adding {len(self._all_markers)} pins and route arrows...", "info")

        route_names = []
        for date_str, routes in self._routes_by_date_trips.items():
            if date_str == self._current_date:
                route_names.extend(routes.keys())
        from utils import get_route_colors
        route_colors = get_route_colors(list(dict.fromkeys(route_names)))

        def add_to_map():
            self._markers_by_trip.clear()
            self._polylines_by_trip.clear()
            polyline_id = 0

            for m in self._all_markers:
                tk = m.get("trip_key", "")
                if self._current_date and not tk.startswith(self._current_date + "|"):
                    continue
                mid = m["id"]
                slinga = tk.split("|")[1] if "|" in tk else ""
                color = route_colors.get(slinga, "#777777")
                name_esc = json.dumps(str(m.get("label", "")))
                info = f"<b>{str(m.get('label', ''))}</b><br>{str(m.get('address', ''))}"
                info_esc = json.dumps(info)
                self._map_view.page().runJavaScript(
                    f"addPin({mid}, {m['lat']}, {m['lng']}, {name_esc}, {json.dumps(color)}, {info_esc}, '#FFFFFF', 0, 0);"
                )
                if tk not in self._markers_by_trip:
                    self._markers_by_trip[tk] = []
                self._markers_by_trip[tk].append(mid)

            from utils import _get_trip_visits
            for date_str, routes in self._routes_by_date_trips.items():
                if date_str != self._current_date:
                    continue
                for slinga, trips in routes.items():
                    for trip_idx, trip_item in enumerate(trips):
                        trip_visits = _get_trip_visits(trip_item)
                        tk = self._trip_key(date_str, slinga, trip_idx)
                        path = []
                        for v in trip_visits:
                            addr = (v.get("adress") or "").strip()
                            if addr and addr in addr_to_coords:
                                lat, lng = addr_to_coords[addr]
                                path.append([lat, lng])
                        if len(path) >= 2:
                            color = route_colors.get(slinga, "#777777")
                            path_js = json.dumps(path)
                            self._map_view.page().runJavaScript(
                                f"addPolyline({polyline_id}, {path_js}, {json.dumps(color)});"
                            )
                            self._polylines_by_trip[tk] = polyline_id
                            polyline_id += 1

            self._update_map_visibility()
            self._log(f"Routes Map: {len(self._markers_by_trip)} trips displayed.", "success")
            default_addr = self._default_address
            if default_addr and default_addr in addr_to_coords and not self._initial_pins_added:
                self._initial_pins_added = True
                lat, lng = addr_to_coords[default_addr]
                self._map_view.page().runJavaScript(f"flyToPin({lat}, {lng});")

        def check_ready(result):
            if result and self._all_markers:
                add_to_map()
            else:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(200, lambda: self._map_view.page().runJavaScript("window.mapReady", check_ready))

        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, lambda: self._map_view.page().runJavaScript("window.mapReady", check_ready))
