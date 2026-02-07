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
)
from PySide6.QtCore import Qt, QUrl, Signal, QTimer
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
        self._arrow_btn = QPushButton("▼" if initial_expanded else "▶")
        self._arrow_btn.setFixedSize(22, 22)
        self._arrow_btn.setFlat(True)
        self._arrow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow_btn.setStyleSheet("font-size: 8pt; padding: 0; border: none;")
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
        self._arrow_btn.setText("▼" if self._expanded else "▶")

    def set_expanded(self, expanded: bool):
        if self._expanded != expanded:
            self._toggle()

    def content_layout(self):
        return self._content_layout


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

        # --- Left: Customer table ---
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.addWidget(QLabel("Customers"))
        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table_layout.addWidget(self._table)
        splitter.addWidget(table_widget)

        # --- Right: Map ---
        from utils import config_disable_webengine_map
        use_webengine = HAS_WEBENGINE and not config_disable_webengine_map()
        if use_webengine:
            import sys
            self._map_view = QWebEngineView()
            self._map_view.setMinimumWidth(400)
            if MapPage:
                self._map_page = MapPage(self._map_view)
                self._map_view.setPage(self._map_page)
                self._map_page.pinClicked.connect(self._on_pin_clicked)
                self._map_page.renderProcessTerminated.connect(self._on_render_process_terminated)
            splitter.addWidget(self._map_view)
        else:
            self._map_view = None
            self._map_page = None
            placeholder = QFrame()
            placeholder.setStyleSheet("background-color: #e5e5e5; border-radius: 8px;")
            placeholder.setMinimumSize(400, 300)
            pl_layout = QVBoxLayout(placeholder)
            pl_layout.addWidget(QLabel(
                "Install pyside6-addons for map display:\n"
                "pip install pyside6-addons"
            ))
            splitter.addWidget(placeholder)

        splitter.setSizes([350, 650])
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
        for c in range(len(cols)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
        self._table.resizeColumnsToContents()
        self._table.setSortingEnabled(True)

    def _on_render_process_terminated(self, status, exit_code: int) -> None:
        """WebEngine render process crashed - show fallback instead of crashing."""
        from PySide6.QtWebEngineCore import QWebEnginePage
        if status != QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            self._log("Map render process ended unexpectedly. Refresh the map if needed.", "warn")

    def _on_pin_clicked(self, marker_id: int) -> None:
        """Pin clicked: select row and zoom to pin. Zoom is done from Python so the map doesn't pan
        during the click (which could cause a spurious click on another pin, e.g. the default)."""
        self._selection_blocked = True
        for row in range(self._table.rowCount()):
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None and item.data(MARKER_INDEX_ROLE) == marker_id:
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

    def _on_table_selection_changed(self) -> None:
        """Table selection changed: move to pin (no zoom change) and highlight."""
        if self._selection_blocked or not self._markers or not HAS_WEBENGINE or not self._map_view:
            return
        rows = self._table.selectedItems()
        if not rows:
            return
        item = rows[0]
        marker_id = item.data(MARKER_INDEX_ROLE)
        if marker_id is None or marker_id >= len(self._markers):
            return
        m = self._markers[marker_id]
        self._map_view.page().runJavaScript(f"moveToPin({m['lat']}, {m['lng']}); highlightPin({marker_id});")

    def _start_geocoding(self) -> None:
        """Geocode addresses in background and update map."""
        from PySide6.QtCore import QThread
        from utils import (
            geocode_addresses,
            load_google_maps_api_key,
            start_map_server,
            get_map_url,
            config_prefer_leaflet_map,
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
        prefer_leaflet = config_prefer_leaflet_map()

        if not api_key and HAS_WEBENGINE and self._map_view:
            self._show_no_api_key_error()
            self._log("No API key - set GOOGLE_MAPS_API_KEY or config.json", "error")
            self._worker = GeocodeWorker(self._address_df, "", self._log)
            self._worker.logMessage.connect(self._log, Qt.ConnectionType.QueuedConnection)
            self._worker.finished.connect(self._on_geocoding_done)
            self._worker.start()
            return

        use_google = (
            api_key
            and not prefer_leaflet
            and start_map_server(api_key)
            and HAS_WEBENGINE
            and self._map_view
        )
        if use_google:
            try:
                self._map_view.setUrl(QUrl(get_map_url()))
                self._map_view.page().loadFinished.connect(self._on_map_load_finished)
            except Exception as e:
                self._log(f"Map load failed: {e}. Using Leaflet.", "warn")
                prefer_leaflet = True
                use_google = False

        if not use_google:
            self._worker = GeocodeWorker(self._address_df, api_key, self._log)
            self._worker.logMessage.connect(self._log, Qt.ConnectionType.QueuedConnection)
            self._worker.finished.connect(self._on_geocoding_done)
            self._worker.start()

    def _show_no_api_key_error(self) -> None:
        """Show error overlay when no API key."""
        if not self._map_view:
            return
        html = """
        <html><body style="margin:0;display:flex;align-items:center;justify-content:center;height:100vh;background:#1e1e1e;color:#f48771;font-family:sans-serif;">
        <div style="text-align:center;padding:20px;">
        <h2>Google Maps API key required</h2>
        <p>Set GOOGLE_MAPS_API_KEY env var or add key to config.json</p>
        <p>Using Leaflet fallback when geocoding completes.</p>
        </div></body></html>
        """
        self._map_view.setHtml(html)

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

    def _on_geocoding_done(self) -> None:
        """Update map with geocoded markers (Leaflet fallback)."""
        from utils import render_customer_map

        from utils import apply_offset_for_overlapping_pins
        self._markers = apply_offset_for_overlapping_pins(self._worker.result)
        if not HAS_WEBENGINE or not self._map_view:
            self._log("Customer List Map: Map not available.", "error")
            return

        if not self._markers:
            self._log("Customer List Map: No pins - geocoding failed for all addresses.", "error")
            html = render_customer_map([])
        else:
            lats = [m["lat"] for m in self._markers]
            lngs = [m["lng"] for m in self._markers]
            center_lat = sum(lats) / len(lats)
            center_lng = sum(lngs) / len(lngs)
            html = render_customer_map(self._markers, center_lat, center_lng)
            self._log(f"Customer List Map: {len(self._markers)} pins on map.", "success")

        self._map_view.setHtml(html)
        if self._markers and self._table.rowCount() > 0 and not self._initial_pins_added:
            self._initial_pins_added = True
            self._selection_blocked = True
            self._table.selectRow(0)
            self._selection_blocked = False

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

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Route Rules Editor")
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
        self.close()


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

        from utils import build_routes_by_date, get_default_route_address, split_route_into_trips
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

        # --- Left: Routes list ---
        left = QWidget()
        left_layout = QVBoxLayout(left)

        if len(self._dates) > 1:
            date_row = QHBoxLayout()
            date_row.addWidget(QLabel("Date:"))
            self._date_combo = QComboBox()
            for d in self._dates:
                self._date_combo.addItem(d, d)
            self._date_combo.currentIndexChanged.connect(self._on_date_changed)
            date_row.addWidget(self._date_combo)
            left_layout.addLayout(date_row)

        sel_row = QHBoxLayout()
        btn_select_all = QPushButton("Select all")
        btn_select_all.setFlat(True)
        btn_select_all.setStyleSheet("QPushButton { font-size: 9pt; padding: 2px 6px; min-width: 0; }")
        btn_select_all.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_select_all.setFixedWidth(btn_select_all.fontMetrics().horizontalAdvance("Select all") + 14)
        btn_select_all.clicked.connect(self._on_select_all)
        btn_deselect_all = QPushButton("Deselect all")
        btn_deselect_all.setFlat(True)
        btn_deselect_all.setStyleSheet("QPushButton { font-size: 9pt; padding: 2px 6px; min-width: 0; }")
        btn_deselect_all.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_deselect_all.setFixedWidth(btn_deselect_all.fontMetrics().horizontalAdvance("Deselect all") + 14)
        btn_deselect_all.clicked.connect(self._on_deselect_all)
        sel_row.addWidget(btn_select_all)
        sel_row.addWidget(btn_deselect_all)
        left_layout.addLayout(sel_row)

        self._trip_buttons_widget = QWidget()
        self._trip_buttons_layout = QHBoxLayout(self._trip_buttons_widget)
        self._trip_buttons_layout.setContentsMargins(0, 4, 0, 4)
        left_layout.addWidget(self._trip_buttons_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(320)
        scroll_widget = QWidget()
        self._routes_scroll_layout = QVBoxLayout(scroll_widget)
        scroll.setWidget(scroll_widget)
        left_layout.addWidget(scroll)
        splitter.addWidget(left)

        # --- Right: Map ---
        from utils import config_disable_webengine_map
        use_webengine = HAS_WEBENGINE and not config_disable_webengine_map()
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
            splitter.addWidget(self._map_view)
        else:
            self._map_view = None
            pl = QFrame()
            pl.setStyleSheet("background-color: #e5e5e5; border-radius: 8px;")
            pl.setMinimumSize(500, 400)
            pl_layout = QVBoxLayout(pl)
            pl_layout.addWidget(QLabel("Install pyside6-addons for map display"))
            splitter.addWidget(pl)

        splitter.setSizes([380, 750])
        layout.addWidget(splitter)

        self._populate_routes_list()
        if self._route_df.empty or not self._routes_by_date:
            self._log("No route data to display.", "warn")
        else:
            self._log("Routes Map: Geocoding addresses...", "info")
            self._start_geocoding()

    def _trip_key(self, date_str: str, slinga: str, trip_idx: int) -> str:
        return f"{date_str}|{slinga}|{trip_idx}"

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
        from utils import get_route_colors
        route_colors = get_route_colors(route_names)
        for slinga, trips in sorted(routes_trips.items()):
            color = route_colors.get(slinga, "#777777")
            route_section = CollapsibleSection(slinga, initial_expanded=False, header_color=color)
            self._route_sections[slinga] = route_section
            group_layout = route_section.content_layout()
            for trip_idx, trip_visits in enumerate(trips):
                tk = self._trip_key(self._current_date, slinga, trip_idx)
                visible = self._trip_visibility.get(tk, True)
                self._trip_visibility[tk] = visible

                trip_label = f"Trip {trip_idx + 1}" if len(trips) > 1 else "Show on map"
                cb = QCheckBox("Show on map")
                cb.setChecked(visible)
                cb.stateChanged.connect(lambda s, k=tk: self._on_trip_toggle(k, s == 2))
                trip_section = CollapsibleSection(trip_label, header_widgets=[cb], initial_expanded=False)
                self._trip_sections[tk] = trip_section
                trip_layout = trip_section.content_layout()

                table = QTableWidget()
                table.setColumnCount(3)
                table.setHorizontalHeaderLabels(["Time", "Address", "Name"])
                table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                hh = table.horizontalHeader()
                for c in range(3):
                    hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
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
        """Build Trip 1, Trip 2, ... Select/Deselect buttons based on max trips."""
        while self._trip_buttons_layout.count():
            item = self._trip_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._current_date or self._current_date not in self._routes_by_date_trips:
            return

        routes_trips = self._routes_by_date_trips[self._current_date]
        max_trips = max(len(trips) for trips in routes_trips.values()) if routes_trips else 0

        _btn_style = "font-size: 8pt; padding: 2px 4px; min-width: 0;"
        for trip_num in range(1, max_trips + 1):
            trip_idx = trip_num - 1
            lbl = QLabel(f"T{trip_num}:")
            lbl.setStyleSheet("font-size: 8pt;")
            self._trip_buttons_layout.addWidget(lbl)
            btn_sel = QPushButton("On")
            btn_sel.setFlat(True)
            btn_sel.setStyleSheet(_btn_style)
            btn_sel.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn_sel.clicked.connect(lambda checked, idx=trip_idx: self._on_select_trip_n(idx))
            btn_desel = QPushButton("Off")
            btn_desel.setFlat(True)
            btn_desel.setStyleSheet(_btn_style)
            btn_desel.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn_desel.clicked.connect(lambda checked, idx=trip_idx: self._on_deselect_trip_n(idx))
            self._trip_buttons_layout.addWidget(btn_sel)
            self._trip_buttons_layout.addWidget(btn_desel)
        self._trip_buttons_layout.addStretch()

    def _on_select_trip_n(self, trip_idx: int) -> None:
        """Select all trips with given index (0-based) across all routes."""
        for tk in self._trip_visibility:
            parts = tk.rsplit("|", 1)
            if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) == trip_idx:
                self._trip_visibility[tk] = True
        self._refresh_trip_checkboxes()
        self._update_map_visibility()

    def _on_deselect_trip_n(self, trip_idx: int) -> None:
        """Deselect all trips with given index (0-based) across all routes."""
        for tk in self._trip_visibility:
            parts = tk.rsplit("|", 1)
            if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) == trip_idx:
                self._trip_visibility[tk] = False
        self._refresh_trip_checkboxes()
        self._update_map_visibility()

    def _on_date_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._dates):
            self._current_date = self._dates[idx]
            self._populate_routes_list()
            self._update_map_visibility()

    def _on_trip_toggle(self, trip_key: str, visible: bool) -> None:
        self._trip_visibility[trip_key] = visible
        self._update_map_visibility()

    def _on_render_process_terminated(self, status, exit_code: int) -> None:
        """WebEngine render process crashed."""
        from PySide6.QtWebEngineCore import QWebEnginePage
        if status != QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            self._log("Map render process ended unexpectedly. Refresh the map if needed.", "warn")

    def _on_pin_clicked(self, marker_id: int) -> None:
        """Pin clicked: expand route/trip, select the corresponding visit row, move and highlight.
        From Python, deferred, so map doesn't pan during the click (like customer map)."""
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
        self._route_selection_blocked = True
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

    def _on_route_table_selection_changed(self) -> None:
        """Visit row selected: zoom to that pin if trip is visible."""
        if self._route_selection_blocked:
            return
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

    def _start_geocoding(self) -> None:
        """Geocode unique addresses and update map."""
        from PySide6.QtCore import QThread
        from utils import (
            geocode_route_addresses,
            load_google_maps_api_key,
            start_map_server,
            get_map_url,
            config_prefer_leaflet_map,
        )

        addresses = []
        self._visit_address_map = []  # [(date, slinga, trip_idx, visit_idx_in_trip, address)]
        for date_str, routes in self._routes_by_date_trips.items():
            for slinga, trips in routes.items():
                for trip_idx, trip_visits in enumerate(trips):
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
        prefer_leaflet = config_prefer_leaflet_map()

        self._use_google_map = (
            api_key
            and not prefer_leaflet
            and start_map_server(api_key)
            and HAS_WEBENGINE
            and self._map_view
        )
        if self._use_google_map:
            try:
                self._map_view.setUrl(QUrl(get_map_url()))
                self._map_view.page().loadFinished.connect(
                    lambda: self._run_geocode_and_update(api_key, unique_addrs)
                )
            except Exception as e:
                self._log(f"Map load failed: {e}", "warn")
                self._use_google_map = False
                self._run_geocode_and_update(api_key, unique_addrs)
        else:
            self._run_geocode_and_update(api_key, unique_addrs)

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
        from utils import get_map_url, render_routes_map
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
            trip_visits = trips[trip_idx] if trip_idx < len(trips) else []
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

        if not self._use_google_map and self._map_view:
            from utils import get_route_colors
            route_names = []
            for date_str, routes in self._routes_by_date_trips.items():
                if date_str == self._current_date:
                    route_names.extend(routes.keys())
            route_colors = get_route_colors(list(dict.fromkeys(route_names)))
            markers_leaflet = []
            polylines_leaflet = []
            for m in self._all_markers:
                addr = m.get("address")
                tk = m.get("trip_key", "")
                if addr in addr_to_coords and self._current_date and tk.startswith(self._current_date + "|"):
                    lat, lng = addr_to_coords[addr]
                    slinga = tk.split("|")[1] if "|" in tk else ""
                    color = route_colors.get(slinga, "#777777")
                    markers_leaflet.append({"lat": lat, "lng": lng, "label": m.get("label", ""), "address": addr, "color": color})
            for date_str, routes in self._routes_by_date_trips.items():
                if date_str != self._current_date:
                    continue
                for slinga, trips in routes.items():
                    for trip_idx, trip_visits in enumerate(trips):
                        path = []
                        for v in trip_visits:
                            addr = (v.get("adress") or "").strip()
                            if addr in addr_to_coords:
                                lat, lng = addr_to_coords[addr]
                                path.append([lat, lng])
                        if len(path) >= 2:
                            color = route_colors.get(slinga, "#777777")
                            polylines_leaflet.append({"path": path, "color": color})
            default_addr = self._default_address
            if default_addr and default_addr in addr_to_coords:
                clat, clng = addr_to_coords[default_addr]
            else:
                lat_list = [m["lat"] for m in markers_leaflet]
                lng_list = [m["lng"] for m in markers_leaflet]
                clat = sum(lat_list) / len(lat_list) if lat_list else 57.71
                clng = sum(lng_list) / len(lng_list) if lng_list else 11.97
            html = render_routes_map(markers_leaflet, polylines_leaflet, clat, clng)
            self._map_view.setHtml(html)
            self._log(f"Routes Map: {len(markers_leaflet)} pins, {len(polylines_leaflet)} routes.", "success")
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

            for date_str, routes in self._routes_by_date_trips.items():
                if date_str != self._current_date:
                    continue
                for slinga, trips in routes.items():
                    for trip_idx, trip_visits in enumerate(trips):
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
