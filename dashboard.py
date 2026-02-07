"""
Main Dashboard (Launcher) for the Toolbox application.
File inputs, verification logic, and action buttons.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QScrollArea,
    QComboBox,
    QFrame,
)
from PySide6.QtGui import QFont
from datetime import datetime
from PySide6.QtCore import Qt, Signal, QObject, QThread

from config import AppConfig, Styles
from windows import CustomerListMapWindow, RoutesMapWindow, RuleEditorWindow
from utils import (
    extract_pdf_data,
    validate_address_columns,
    load_route_data,
    export_address_to_csv,
    export_address_to_excel,
    export_route_to_csv,
    export_route_to_excel,
    get_default_route_address,
    get_default_location_name,
    get_route_color_rules,
    save_route_color_rules,
    save_config_updates,
    ROUTE_COLOR_PRESETS,
)


# =============================================================================
# File verification
# =============================================================================


def _is_valid_path(path: str, extensions: set[str]) -> bool:
    """Check if path exists and has an allowed extension."""
    if not path or not path.strip():
        return False
    p = Path(path.strip())
    return p.exists() and p.suffix.lower() in extensions


# =============================================================================
# Background workers
# =============================================================================


class AddressExtractWorker(QObject):
    """Worker to extract address data from PDF in background."""

    finished = Signal(object, str)  # (df or None, error_message)

    def __init__(self, pdf_path: str):
        super().__init__()
        self._path = pdf_path

    def run(self) -> None:
        try:
            df, err = extract_pdf_data(self._path)
            if err:
                self.finished.emit(None, err)
                return
            if df is not None and not df.empty:
                valid, col_err = validate_address_columns(df)
                if valid:
                    self.finished.emit(df, "")
                else:
                    self.finished.emit(None, col_err or "Column validation failed")
            else:
                self.finished.emit(None, "No data extracted from PDF")
        except Exception as e:
            self.finished.emit(None, f"Address extraction error: {type(e).__name__}: {e}")


class RouteLoadWorker(QObject):
    """Worker to load route data in background."""

    finished = Signal(object, str)  # (df or None, error_message)

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self) -> None:
        df, err = load_route_data(self._path)
        self.finished.emit(df, err or "")


# =============================================================================
# Dashboard UI
# =============================================================================


class Dashboard(QMainWindow):
    """
    Main launcher window with file inputs and action buttons.
    Address section: save and map enabled when PDF extracted.
    Route section: save and map enabled when route file loaded.
    Show Routes on Map requires only route data.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{AppConfig.APP_NAME} - Dashboard")
        self.setMinimumSize(560, 520)

        self._address_data = None
        self._route_data = None
        self._address_thread = None
        self._route_thread = None
        self._address_path_in_progress = None
        self._route_path_in_progress = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Top bar: spacer + Settings link ---
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        btn_settings = QPushButton("Settings")
        btn_settings.setFlat(True)
        btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_settings.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #605e5c; font-size: 10pt; padding: 4px 8px; } "
            "QPushButton:hover { color: #0078d4; }"
        )
        btn_settings.setToolTip("Settings")
        btn_settings.clicked.connect(self._on_settings)
        top_bar.addWidget(btn_settings)
        layout.addLayout(top_bar)

        # --- Address Source section ---
        addr_group = QGroupBox("Address Source")
        addr_layout = QVBoxLayout(addr_group)

        addr_row = QHBoxLayout()
        addr_row.addWidget(QLabel("PDF file:"))
        self._address_edit = QLineEdit()
        self._address_edit.setPlaceholderText("Select PDF file...")
        self._address_edit.textChanged.connect(self._on_path_changed)
        addr_row.addWidget(self._address_edit)
        btn_browse_addr = QPushButton("Browse")
        btn_browse_addr.clicked.connect(self._browse_address)
        addr_row.addWidget(btn_browse_addr)
        addr_layout.addLayout(addr_row)

        self._btn_save_address_csv = QPushButton("Save Address CSV")
        self._btn_save_address_csv.setEnabled(False)
        self._btn_save_address_csv.clicked.connect(self._on_save_address_csv)
        addr_layout.addWidget(self._btn_save_address_csv)

        self._btn_save_address_excel = QPushButton("Save Address Excel")
        self._btn_save_address_excel.setEnabled(False)
        self._btn_save_address_excel.clicked.connect(self._on_save_address_excel)
        addr_layout.addWidget(self._btn_save_address_excel)

        self._btn_customer_map = QPushButton("Show Customer List on Map")
        self._btn_customer_map.setEnabled(False)
        self._btn_customer_map.clicked.connect(self._on_show_customer_map)
        addr_layout.addWidget(self._btn_customer_map)

        layout.addWidget(addr_group)

        # --- Route Data section ---
        route_group = QGroupBox("Route Data")
        route_layout = QVBoxLayout(route_group)

        route_row = QHBoxLayout()
        route_row.addWidget(QLabel("Excel file:"))
        self._route_edit = QLineEdit()
        self._route_edit.setPlaceholderText("Select Excel file...")
        self._route_edit.textChanged.connect(self._on_path_changed)
        route_row.addWidget(self._route_edit)
        btn_browse_route = QPushButton("Browse")
        btn_browse_route.clicked.connect(self._browse_route)
        route_row.addWidget(btn_browse_route)
        route_layout.addLayout(route_row)

        self._btn_save_route_csv = QPushButton("Save Route CSV")
        self._btn_save_route_csv.setEnabled(False)
        self._btn_save_route_csv.clicked.connect(self._on_save_route_csv)
        route_layout.addWidget(self._btn_save_route_csv)

        self._btn_save_route_excel = QPushButton("Save Route Excel")
        self._btn_save_route_excel.setEnabled(False)
        self._btn_save_route_excel.clicked.connect(self._on_save_route_excel)
        route_layout.addWidget(self._btn_save_route_excel)

        self._btn_routes_map = QPushButton("Show Routes on Map")
        self._btn_routes_map.setEnabled(False)
        self._btn_routes_map.clicked.connect(self._on_show_routes_map)
        route_layout.addWidget(self._btn_routes_map)

        btn_edit_rules = QPushButton("Edit route rules")
        btn_edit_rules.clicked.connect(self._on_edit_rules)
        route_layout.addWidget(btn_edit_rules)

        layout.addWidget(route_group)

        # --- Status console (colored output) ---
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        self._status_console = QTextEdit()
        self._status_console.setReadOnly(True)
        self._status_console.setMinimumHeight(120)
        self._status_console.setFont(QFont("Consolas", 10))
        self._status_console.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "border: 1px solid #3b3a39; border-radius: 8px; "
            "padding: 8px;"
        )
        self._status_console.setPlaceholderText("Ready. Select files to begin.")
        status_layout.addWidget(self._status_console)
        layout.addWidget(status_group)

        # Initial state
        self.log("Application started.", "info")
        self._update_verification()

    def log(self, message: str, level: str = "info") -> None:
        """Append a timestamped, colored message to the status console."""
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {
            "info": "#d4d4d4",
            "success": "#4ec9b0",
            "error": "#f48771",
            "warn": "#dcdcaa",
        }
        color = colors.get(level, colors["info"])
        html = f'<span style="color:#858585">[{ts}]</span> <span style="color:{color}">{self._escape_html(message)}</span>'
        self._status_console.append(html)

    def _escape_html(self, s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _update_buttons(self) -> None:
        """Enable/disable buttons based on available data."""
        addr_ready = self._address_data is not None
        route_ready = self._route_data is not None

        self._btn_save_address_csv.setEnabled(addr_ready)
        self._btn_save_address_excel.setEnabled(addr_ready)
        self._btn_save_route_csv.setEnabled(route_ready)
        self._btn_save_route_excel.setEnabled(route_ready)
        self._btn_customer_map.setEnabled(addr_ready)
        self._btn_routes_map.setEnabled(route_ready)

    def _browse_address(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Address Source File", "", "PDF (*.pdf)",
        )
        if path:
            self._address_edit.setText(path)

    def _browse_route(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Route Data File", "", "Excel (*.xlsx *.xls)",
        )
        if path:
            self._route_edit.setText(path)

    def _on_path_changed(self, _text: str) -> None:
        self._update_verification()

    def _update_verification(self) -> None:
        addr_path = self._address_edit.text().strip()
        route_path = self._route_edit.text().strip()

        # Reset data when path changes
        if not _is_valid_path(addr_path, AppConfig.ADDRESS_SOURCE_EXTENSIONS):
            self._address_data = None
            self._address_thread = None
        if not _is_valid_path(route_path, AppConfig.ROUTE_DATA_EXTENSIONS):
            self._route_data = None
            self._route_thread = None

        self._update_buttons()

        # Start address extraction if valid PDF
        if addr_path and _is_valid_path(addr_path, AppConfig.ADDRESS_SOURCE_EXTENSIONS):
            self.log(f"Extracting address data from PDF...", "info")
            self._start_address_extraction(addr_path)

        # Start route load if valid file
        if route_path and _is_valid_path(route_path, AppConfig.ROUTE_DATA_EXTENSIONS):
            self.log(f"Loading route data from {Path(route_path).name}...", "info")
            self._start_route_load(route_path)

    def _start_address_extraction(self, path: str) -> None:
        if self._address_thread and self._address_thread.isRunning():
            return
        self._address_path_in_progress = path
        self._address_thread = QThread()
        self._addr_worker = AddressExtractWorker(path)
        self._addr_worker.moveToThread(self._address_thread)
        self._address_thread.started.connect(self._addr_worker.run)
        self._addr_worker.finished.connect(self._on_address_extracted)
        self._addr_worker.finished.connect(self._address_thread.quit)
        self._address_thread.start()

    def _on_address_extracted(self, df, error: str) -> None:
        if Path(self._address_edit.text().strip()) != Path(self._address_path_in_progress or ""):
            return
        self._address_path_in_progress = None
        if error:
            self.log(f"Address extraction failed: {error}", "error")
            self._address_data = None
        else:
            self.log(f"Address data extracted. {len(df)} rows. Columns validated: {', '.join(AppConfig.ADDRESS_SOURCE_COLUMNS)}", "success")
            self._address_data = df
        self._update_buttons()

    def _start_route_load(self, path: str) -> None:
        if self._route_thread and self._route_thread.isRunning():
            return
        self._route_path_in_progress = path
        self._route_thread = QThread()
        self._route_worker = RouteLoadWorker(path)
        self._route_worker.moveToThread(self._route_thread)
        self._route_thread.started.connect(self._route_worker.run)
        self._route_worker.finished.connect(self._on_route_loaded)
        self._route_worker.finished.connect(self._route_thread.quit)
        self._route_thread.start()

    def _on_route_loaded(self, df, error: str) -> None:
        if Path(self._route_edit.text().strip()) != Path(self._route_path_in_progress or ""):
            return
        self._route_path_in_progress = None
        if error:
            self.log(f"Route load failed: {error}", "error")
            self._route_data = None
        else:
            self.log(
                f"Route data loaded. {len(df)} rows. Columns: {', '.join(AppConfig.ROUTE_DATA_COLUMNS)}",
                "success",
            )
            self._route_data = df
        self._update_buttons()

    # --- Action handlers ---

    def _on_save_address_csv(self) -> None:
        if self._address_data is None:
            self.log("No address data to save.", "error")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Address CSV",
            str(Path(AppConfig.DEFAULT_EXPORT_DIR) / "address_export.csv"),
            "CSV (*.csv)"
        )
        if path:
            try:
                export_address_to_csv(self._address_data, path)
                self.log(f"Address data saved to {path}", "success")
            except Exception as e:
                self.log(f"Save failed: {e}", "error")

    def _on_save_address_excel(self) -> None:
        if self._address_data is None:
            self.log("No address data to save.", "error")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Address Excel",
            str(Path(AppConfig.DEFAULT_EXPORT_DIR) / "address_export.xlsx"),
            "Excel (*.xlsx)"
        )
        if path:
            try:
                export_address_to_excel(self._address_data, path)
                self.log(f"Address data saved to {path}", "success")
            except Exception as e:
                self.log(f"Save failed: {e}", "error")

    def _on_save_route_csv(self) -> None:
        if self._route_data is None:
            self.log("No route data to save.", "error")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Route CSV",
            str(Path(AppConfig.DEFAULT_EXPORT_DIR) / "route_export.csv"),
            "CSV (*.csv)"
        )
        if path:
            try:
                export_route_to_csv(self._route_data, path)
                self.log(f"Route data saved to {path}", "success")
            except Exception as e:
                self.log(f"Save failed: {e}", "error")

    def _on_save_route_excel(self) -> None:
        if self._route_data is None:
            self.log("No route data to save.", "error")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Route Excel",
            str(Path(AppConfig.DEFAULT_EXPORT_DIR) / "route_export.xlsx"),
            "Excel (*.xlsx)"
        )
        if path:
            try:
                export_route_to_excel(self._route_data, path)
                self.log(f"Route data saved to {path}", "success")
            except Exception as e:
                self.log(f"Save failed: {e}", "error")

    def _on_show_customer_map(self) -> None:
        self.log("Opening Customer List on Map...", "info")
        win = CustomerListMapWindow(self._address_data, self, log_fn=self.log)
        win.show()

    def _on_show_routes_map(self) -> None:
        self.log("Opening Routes on Map...", "info")
        win = RoutesMapWindow(self._route_data, self, log_fn=self.log)
        win.show()

    def _on_edit_rules(self) -> None:
        win = RuleEditorWindow(self)
        win.show()

    def _on_settings(self) -> None:
        """Open Settings dialog (default address, location name, route colors, etc.)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setMinimumWidth(480)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("Default address for route visits with no address:"))
        addr_edit = QLineEdit()
        addr_edit.setText(get_default_route_address())
        addr_edit.setPlaceholderText("e.g. Angereds Torg 5, 42465 Angered")
        layout.addWidget(addr_edit)

        layout.addWidget(QLabel("Display name for default location (Kontor, office, etc.):"))
        name_edit = QLineEdit()
        name_edit.setText(get_default_location_name())
        name_edit.setPlaceholderText("e.g. Kontor")
        layout.addWidget(name_edit)

        # Route color rules
        color_group = QGroupBox("Route colors")
        color_layout = QVBoxLayout(color_group)
        color_layout.addWidget(QLabel("Use color if route name contains (first match wins):"))
        rules_widget = QWidget()
        rules_layout = QVBoxLayout(rules_widget)
        rules_layout.setContentsMargins(0, 0, 0, 0)
        rule_rows = []

        def add_rule_row(rule=None):
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            color_combo = QComboBox()
            for preset_name, hex_val in ROUTE_COLOR_PRESETS:
                color_combo.addItem(preset_name, hex_val)
            color_combo.setMinimumWidth(120)
            contains_edit = QLineEdit()
            contains_edit.setPlaceholderText("e.g. A, B, Nord")
            contains_edit.setMinimumWidth(140)
            remove_btn = QPushButton("Remove")
            remove_btn.setFlat(True)
            remove_btn.setStyleSheet("font-size: 9pt; padding: 2px 6px;")
            if rule:
                rule_color = (rule.get("color") or "").strip()
                found = False
                for i in range(color_combo.count()):
                    if (color_combo.itemData(i) or "").lower() == rule_color.lower():
                        color_combo.setCurrentIndex(i)
                        found = True
                        break
                if not found and rule_color:
                    color_combo.addItem(rule_color, rule_color)
                    color_combo.setCurrentIndex(color_combo.count() - 1)
                contains_edit.setText(rule.get("contains", ""))
            row_layout.addWidget(QLabel("Use"))
            row_layout.addWidget(color_combo)
            row_layout.addWidget(QLabel("if route name contains:"))
            row_layout.addWidget(contains_edit)
            row_layout.addWidget(remove_btn)
            row_layout.addStretch()

            def remove_row():
                rules_layout.removeWidget(row)
                row.deleteLater()
                rule_rows.remove((row, color_combo, contains_edit))

            remove_btn.clicked.connect(remove_row)
            rules_layout.addWidget(row)
            rule_rows.append((row, color_combo, contains_edit))

        for rule in get_route_color_rules():
            add_rule_row(rule)
        if not rule_rows:
            add_rule_row()

        add_btn = QPushButton("Add rule")
        add_btn.setFlat(True)
        add_btn.clicked.connect(lambda: add_rule_row())
        rules_layout.addWidget(add_btn)

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(0, 0, 0, 0)
        scroll_content_layout.addWidget(rules_widget)  # no stretch - stays compact
        scroll_content_layout.addStretch(1)  # extra space goes here, not between rows

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setMinimumHeight(120)
        color_layout.addWidget(scroll, 1)  # stretch=1 so list grows when window grows
        layout.addWidget(color_group, 1)  # stretch=1 so group (and scroll) grows when dialog grows

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            updates = {}
            if addr_edit.text().strip():
                updates["default_route_address"] = addr_edit.text().strip()
            if name_edit.text().strip():
                updates["default_location_name"] = name_edit.text().strip()
            if updates:
                save_config_updates(updates)
            rules = []
            for _, color_combo, contains_edit in rule_rows:
                contains = contains_edit.text().strip()
                if contains:
                    color = color_combo.currentData() or "#777777"
                    rules.append({"color": color, "contains": contains})
            save_route_color_rules(rules)
            self.log("Settings saved.", "success")
