"""
Customer List Map Window - displays customer addresses on a map.
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
    QScrollArea,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QUrl, Signal, QTimer, QThread
from PySide6.QtGui import QBrush

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

from config import AppConfig
from windows_common import (
    HAS_WEBENGINE,
    MapPage,
    MARKER_INDEX_ROLE,
    CUSTOM_PIN_ID_BASE,
    CustomerTableDelegate,
    CustomAddressesSection,
    _add_default_customer,
)
from utils import (
    config_disable_webengine_map,
    geocode_addresses,
    load_google_maps_api_key,
    start_map_server,
    get_map_url,
    apply_offset_for_overlapping_pins,
    parse_color_for_marker,
    text_color_for_background,
    title_case_display,
)


class CustomerListMapWindow(QMainWindow):
    """
    Window for displaying customer list on map.
    Customer list on left (sortable), map with colored pins on right.
    """

    def __init__(self, address_df, parent=None, log_fn=None):
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
        use_webengine = HAS_WEBENGINE and not config_disable_webengine_map()
        self._map_stack = QStackedWidget()
        if use_webengine and QWebEngineView:
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
        df = self._address_df
        cols = AppConfig.ADDRESS_SOURCE_COLUMNS
        self._table.setSortingEnabled(False)
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.setRowCount(len(df))

        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QHeaderView

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
        import json

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
                QTimer.singleShot(200, lambda: self._map_view.page().runJavaScript("window.mapReady", check_ready))

        QTimer.singleShot(500, lambda: self._map_view.page().runJavaScript("window.mapReady", check_ready))
