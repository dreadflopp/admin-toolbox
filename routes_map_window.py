"""
Routes Map Window - displays route visits on a map with trip grouping.
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
    QPushButton,
    QSizePolicy,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QUrl, QTimer, QThread

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

from windows_common import (
    HAS_WEBENGINE,
    MapPage,
    VISIT_ROLE,
    CUSTOM_PIN_ID_BASE,
    CollapsibleSection,
    CustomAddressesSection,
)
from utils import (
    config_disable_webengine_map,
    build_routes_by_date,
    get_default_route_address,
    split_route_into_trips,
    get_route_colors,
    sort_routes_for_display,
    _get_trip_visits,
    get_route_sort_order,
    save_route_sort_order,
    get_default_location_name,
    load_google_maps_api_key,
    start_map_server,
    get_map_url,
    geocode_route_addresses,
    TRIP_NAMES,
)
from PySide6.QtWidgets import QHeaderView


class RoutesMapWindow(QMainWindow):
    """
    Window for displaying routes on map.
    Left: routes list with visits (time, address). Each route has checkbox to toggle.
    Right: map with pins and arrows between consecutive visits.
    Date selector when data spans multiple days.
    """

    def __init__(self, route_df, parent=None, log_fn=None):
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
        sel_row.addWidget(btn_expand_all)
        sel_row.addWidget(btn_collapse_all)
        sel_row.addSpacing(12)
        sel_row.addWidget(QLabel("Sort:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("By name", "name")
        self._sort_combo.addItem("By first trip", "time")
        self._sort_combo.setStyleSheet("font-size: 9pt; min-width: 110px;")
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
        use_webengine = HAS_WEBENGINE and not config_disable_webengine_map()
        self._map_stack = QStackedWidget()
        if use_webengine and QWebEngineView:
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
            trip_visits = _get_trip_visits(trip_item) if trip_item else []
            visit = trip_visits[visit_idx] if visit_idx < len(trip_visits) else {}
            raw_namn = visit.get("namn", addr[:30])
            s = str(raw_namn).strip().lower() if raw_namn is not None else ""
            label = "" if (not s or s in ("nan", "none")) else str(raw_namn).strip()
            if not label:
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
                QTimer.singleShot(200, lambda: self._map_view.page().runJavaScript("window.mapReady", check_ready))

        QTimer.singleShot(500, lambda: self._map_view.page().runJavaScript("window.mapReady", check_ready))
